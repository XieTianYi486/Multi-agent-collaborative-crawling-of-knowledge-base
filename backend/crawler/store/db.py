"""数据库连接与会话管理（爬虫侧独立 SQLite）。"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..settings import DATA_DIR
from .models import Base

_engine = None
_SessionLocal: sessionmaker | None = None


def get_db_path() -> Path:
    return DATA_DIR / "db" / "crawler.db"


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
        _set_pragmas(_engine)
        # expire_on_commit=False：提交后对象属性仍可用（跨步骤传递数据）
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def _set_pragmas(engine) -> None:
    """WAL 模式 + 忙等待：流水线与测试并发使用同一库时不冲突。"""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")  # 写锁忙等待 10 秒
        cursor.close()


def init_db() -> None:
    """建表（幂等）。"""
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope():
    """事务会话：正常提交、异常回滚、最终关闭。"""
    if _SessionLocal is None:
        get_engine()
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
