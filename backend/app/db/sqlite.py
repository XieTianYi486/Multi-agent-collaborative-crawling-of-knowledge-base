# ============================================================
# SQLite 数据库连接管理（同步 SQLAlchemy）
# 与旧项目的 aiosqlite 异步方案区分开
# ============================================================

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from app.core.config import settings

# --- 创建引擎 ---
# SQLite 需要 check_same_thread=False 以支持多线程
connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args["check_same_thread"] = False
    # 写锁等待时间（秒）：并发写入时等待而不是立刻报 "database is locked"
    connect_args["timeout"] = 30

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,  # 开发环境打印 SQL
    # SQLite 是本地文件，不存在"连接失效"问题，pre_ping 只会给每次取连接
    # 多加一条 SELECT 1；连接池放大到 40，避免高并发时排队 30 秒后报错
    pool_size=20,
    max_overflow=20,
    pool_timeout=10,
)

# --- SQLite 特定优化 ---
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """设置连接级 PRAGMA（WAL 由 init_db 在启动时设置一次并持久化）"""
        cursor = dbapi_connection.cursor()
        # 注意：journal_mode 是持久化到数据库文件的属性，不能在每个新连接上执行。
        # 高并发时大量新连接同时执行 PRAGMA journal_mode=WAL 会争抢排他锁，
        # 叠加 busy_timeout=30 会把线程池全部拖死（表现为请求 30 秒后 500）。
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA encoding='UTF-8';")
        cursor.close()
        # 确保文本以 UTF-8 正确处理
        dbapi_connection.text_factory = str

# --- 会话工厂 ---
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,  # 手动控制 flush
    expire_on_commit=False,  # commit 后不使对象过期，避免 detached instance 错误
)

# --- 声明式基类 ---
Base = declarative_base()


def get_db() -> Session:
    """
    FastAPI 依赖注入：获取数据库会话

    使用方式:
        @router.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()

    注意：请求结束时自动关闭会话，异常时自动回滚
    支持端点提前关闭 Session 的场景（如流式响应端点）
    """
    db = SessionLocal()
    try:
        yield db
        try:
            db.commit()  # 正常结束则提交（若 Session 已提前关闭则跳过）
        except Exception:
            pass  # Session 已被端点关闭，忽略提交错误
    except Exception:
        try:
            db.rollback()  # 异常则回滚
        except Exception:
            pass
        raise  # 必须重新抛出端点异常，否则 FastAPI 返回 500 且真实错误被吞掉
    finally:
        try:
            db.close()
        except Exception:
            pass  # Session 可能已关闭，忽略


def init_db():
    """
    初始化数据库：创建所有表，自动迁移新增列
    在应用启动时调用一次
    """
    Base.metadata.create_all(bind=engine)
    # 自动迁移：为已有表添加新列（SQLite ALTER TABLE 兼容）
    _migrate_add_columns(engine)
    _ensure_indexes(engine)
    _ensure_journal_mode(engine)


def _ensure_journal_mode(engine):
    """WAL 是数据库文件的持久属性，启动时设置一次即可。"""
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.commit()


def _ensure_indexes(engine):
    """补充性能索引（create_all 不会为已存在的表创建新索引）。"""
    with engine.connect() as conn:
        # 文档列表固定按「已发布 + 已通过」过滤并按创建时间倒序，
        # 没有该索引时每次都要扫描全表再建临时排序树
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_documents_visible_created "
            "ON documents (status, review_status, created_at)"
        )
        conn.commit()


def _migrate_add_columns(engine):
    """自动为已有表添加缺失的列（无痛迁移）"""
    import sqlite3
    # 通过原始 SQLite 连接执行
    with engine.connect() as conn:
        # 获取 users 表已有列
        result = conn.exec_driver_sql("PRAGMA table_info(users)")
        existing_cols = {row[1] for row in result}
        migrations = [
            ("avatar_url", "TEXT"),
            ("position", "TEXT"),
            ("gender", "TEXT DEFAULT '男'"),
            ("entry_date", "DATE"),
            # 登录安全字段
            ("failed_attempts", "INTEGER DEFAULT 0"),
            ("locked_until", "DATETIME"),
        ]
        for col_name, col_type in migrations:
            if col_name not in existing_cols:
                sql = f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"
                conn.exec_driver_sql(sql)

        # documents 表追加知识审核发布流字段
        doc_result = conn.exec_driver_sql("PRAGMA table_info(documents)")
        doc_cols = {row[1] for row in doc_result}
        doc_migrations = [
            ("review_status", "INTEGER DEFAULT 1"),
            ("reviewed_by", "INTEGER"),
            ("reviewed_at", "DATETIME"),
            ("review_comment", "TEXT"),
            # 爬虫入库溯源字段（幂等去重键）
            ("source_url", "TEXT"),
            ("source_hash", "TEXT"),
        ]
        added_review_col = False
        for col_name, col_type in doc_migrations:
            if col_name not in doc_cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}"
                )
                added_review_col = added_review_col or (col_name == "review_status")

        # 一次性的数据回填：新增 review_status 列后，把已有的"已发布(status=1)"文档
        # 置为"已通过(2)"，避免上线后存量知识全部变不可见
        if added_review_col:
            conn.exec_driver_sql(
                "UPDATE documents SET review_status = 2 WHERE status = 1"
            )

        # source_hash 幂等去重索引：ALTER TABLE 加列不会带索引，这里显式创建
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_documents_source_hash "
            "ON documents(source_hash)"
        )

        # departments 表追加部门类型字段（teaching=教学单位 / class=班级）
        dept_result = conn.exec_driver_sql("PRAGMA table_info(departments)")
        dept_cols = {row[1] for row in dept_result}
        if "dept_type" not in dept_cols:
            conn.exec_driver_sql(
                "ALTER TABLE departments ADD COLUMN dept_type TEXT DEFAULT 'teaching'"
            )

        conn.commit()
