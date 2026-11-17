# ============================================================
# FastAPI 应用入口
# 组装路由、中间件、异常处理、生命周期管理
# ============================================================

from contextlib import asynccontextmanager
import os
from pathlib import Path
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.exceptions import AppException
from app.db.sqlite import init_db, engine

# 导入所有模型确保注册到 SQLAlchemy Base 元数据
import app.models.user      # noqa: F401
import app.models.document  # noqa: F401
import app.models.chat      # noqa: F401
import app.models.ticket    # noqa: F401
import app.models.audit     # noqa: F401
import app.models.api_client  # noqa: F401
import app.models.counselor   # noqa: F401
import app.models.collection  # noqa: F401
import app.models.video       # noqa: F401
import app.models.teaching    # noqa: F401
import app.models.agent_action  # noqa: F401

from app.models.user import Role, User
from app.core.security import hash_password

# ==================== 应用生命周期 ====================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    # 启动时
    print(f"[启动] {settings.APP_NAME} v{settings.APP_VERSION}")

    # 同步端点（SQLAlchemy 同步 Session）跑在 anyio 线程池里，默认只有 40 个令牌。
    # 并发超过这个数时，连接释放和依赖清理拿不到线程，会互相等待，
    # 表现为请求卡住 10 秒后 500。放宽到 80，避免高并发下的线程池饥饿。
    from anyio import to_thread
    to_thread.current_default_thread_limiter().total_tokens = 80

    # 安全自检：非 DEBUG 环境检测到默认密钥/密码/关闭验证码时直接拒绝启动（先于任何数据初始化）
    _assert_production_safety()

    print(f"[启动] 初始化数据库...")

    # 创建所有表
    init_db()

    # 初始化默认数据（角色 + 管理员）
    _init_default_data()

    # 预热本地重排序模型：ONNX 首次加载约 20s，放后台线程避免拖慢启动与首个问答
    _warmup_local_reranker()

    # 预置视频专区数据（仅在视频表为空时写入）
    _init_default_videos()

    # 爬虫子库初始化：新机器/本地包可能没有 crawler/data（运行期数据），
    # 启动时建表并同步站点档案，避免管理端「爬取中心」因缺表返回 500
    _init_crawler_store()

    print(f"[启动] 服务就绪，监听 {settings.HOST}:{settings.PORT}")
    yield
    # 关闭时
    print("[关闭] 正在关闭服务...")
    engine.dispose()


# ==================== 创建应用 ====================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ==================== CORS 中间件 ====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 全局异常处理 ====================


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """处理自定义应用异常"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": exc.detail,
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """处理未捕获的通用异常"""
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "code": 5000,
            "message": "服务器内部错误，请稍后重试",
            "data": None,
        }
    )


# ==================== 注册路由 ====================

from app.api.v1 import (
    auth, documents, chat, admin, tickets, security, crawler, api_clients,
    collection, counselor, videos, notifications, teaching,
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(documents.admin_review_router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(tickets.router, prefix="/api/v1")
app.include_router(tickets.admin_router, prefix="/api/v1")
app.include_router(security.router, prefix="/api/v1")
app.include_router(crawler.router, prefix="/api/v1")
app.include_router(api_clients.router, prefix="/api/v1")
app.include_router(collection.router, prefix="/api/v1")
app.include_router(videos.router, prefix="/api/v1")
app.include_router(videos.admin_router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(teaching.router, prefix="/api/v1")
# AI 助手：由配置开关控制（默认启用）
if settings.COUNSELOR_ENABLED:
    app.include_router(counselor.router, prefix="/api/v1")

# 对外开放 API（API Key 鉴权，命名空间与内部接口隔离）
from app.api.open_api import v1 as open_v1

app.include_router(open_v1.router, prefix="/openapi")

# 挂载爬取导入文档的附件图片目录（仅公开技术资料 security_level=1，独立于用户上传目录）
# 注意：必须先于 /static 挂载——Starlette 按注册顺序做前缀匹配，
# 后注册的 /static 会吞掉所有 /static/import/* 请求导致 404
import_dir = Path(settings.UPLOAD_DIR) / "import_20260919"
if import_dir.exists():
    app.mount("/static/import", StaticFiles(directory=str(import_dir)), name="import_static")

# 挂载静态文件目录（头像等）
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(os.path.join(static_dir, "avatars"), exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ==================== 健康检查 ====================

@app.get("/api/health", tags=["系统"])
def health_check():
    """服务健康检查"""
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


# ==================== 辅助函数 ====================

def _assert_production_safety():
    """
    生产环境安全自检（默认关闭失败）。

    只要检测到占位 JWT 密钥 / 弱管理员口令 / 关闭验证码，一律拒绝启动——
    与 DEBUG 无关，避免"忘了把 DEBUG 改成 false"就让安全防线整体静默失效。
    本地开发如需保留弱口令调试，必须在 .env 显式设置 SKIP_SAFETY_CHECK=true
    （deploy.sh 会强制把该开关写回 false）。
    """
    default_jwt_keys = {"jwt-secret-change-in-production", "jwt-dev-secret-2024"}
    # .env.example 的占位符同样属于公开弱口令，一并拦截
    weak_admin_passwords = {"admin123", "change-this-password", "123456", "admin", "password"}
    problems = []
    if settings.JWT_SECRET_KEY in default_jwt_keys:
        problems.append("JWT_SECRET_KEY 仍为默认值（任何人可伪造登录 Token）")
    if settings.ADMIN_PASSWORD in weak_admin_passwords:
        problems.append("ADMIN_PASSWORD 仍为默认/占位弱口令（admin123 / change-this-password 等）")
    if not settings.CAPTCHA_ENABLED:
        problems.append("CAPTCHA_ENABLED=false（登录验证码被关闭）")

    if not problems:
        return

    if settings.SKIP_SAFETY_CHECK:
        for p in problems:
            print(f"[安全警告] {p}，SKIP_SAFETY_CHECK=true 已豁免，仅限本地开发！")
        return

    raise RuntimeError(
        "检测到不安全生产配置，已拒绝启动：\n  - "
        + "\n  - ".join(problems)
        + "\n请在 backend/.env 中修改后重启（仅本地开发调试可设置 SKIP_SAFETY_CHECK=true 豁免）。"
    )


def _warmup_local_reranker():
    """后台预热本地 ONNX 重排模型（首次加载约 20s，避免落到首个用户请求上）"""
    provider = (settings.RERANK_PROVIDER or "auto").lower()
    use_onnx = provider == "onnx" or (
        provider == "auto" and settings.LLM_PROVIDER.lower() == "local"
    )
    if not use_onnx:
        return

    def _run():
        try:
            from app.rag.reranker.llm_reranker import get_reranker
            reranker = get_reranker()
            ensure = getattr(reranker, "_ensure_loaded", None)
            if callable(ensure):
                ensure()
                print("[启动] 本地重排模型预热完成")
        except Exception as e:
            print(f"[启动] 本地重排模型预热失败（将回退 LLM 排序）: {e}")

    threading.Thread(target=_run, name="reranker-warmup", daemon=True).start()


def _init_default_data():
    """
    初始化默认角色和管理员账号
    幂等：角色按 code 补齐（含学生/老师），默认管理员仅在缺少时创建
    """
    from app.db.sqlite import SessionLocal

    db = SessionLocal()
    try:
        # 预置角色（含学生/老师身份）
        roles = [
            Role(name="超级管理员", code="super_admin",
                 description="拥有系统全部权限",
                 permissions=["*"]),
            Role(name="知识库管理员", code="knowledge_admin",
                 description="管理文档和知识库内容",
                 permissions=["documents:*", "categories:*", "logs:read", "stats:read"]),
            Role(name="院系管理员", code="dept_admin",
                 description="管理院系文档和问答统计",
                 permissions=["documents:read", "stats:read"]),
            Role(name="老师", code="teacher",
                 description="教学人员，可查询知识库内容并投稿教学资料",
                 permissions=["chat:ask", "documents:read", "documents:upload", "stats:read"]),
            Role(name="学生", code="student",
                 description="学生，可查询知识库内容",
                 permissions=["chat:ask", "documents:read"]),
            Role(name="访客", code="employee",
                 description="浏览与检索公开教学资料",
                 permissions=["chat:ask", "documents:read"]),
        ]

        # 幂等补齐：按 code 插入缺失角色（兼容已有数据库）
        existing_roles = {r.code: r for r in db.query(Role).all()}
        for role in roles:
            if role.code not in existing_roles:
                db.add(role)
        db.flush()

        # 老库升级：教师角色补齐文档投稿权限（不覆盖管理员已自定义的其余权限）
        teacher = existing_roles.get("teacher")
        if teacher is not None:
            perms = list(teacher.permissions or [])
            if "documents:upload" not in perms:
                teacher.permissions = perms + ["documents:upload"]
                db.flush()

        # 老库升级：把旧项目（企业制度/劳动法）遗留的角色命名改为教学场景用语
        role_renames = {"dept_admin": "院系管理员", "employee": "访客"}
        for code, name in role_renames.items():
            role = existing_roles.get(code)
            if role is not None and role.name != name:
                role.name = name
                db.flush()

        # 创建默认管理员（仅当不存在任何超级管理员用户时）
        admin_role = db.query(Role).filter(Role.code == "super_admin").first()
        has_admin = (
            db.query(User)
            .join(Role, User.role_id == Role.id)
            .filter(Role.code == "super_admin")
            .first()
            is not None
        )
        if admin_role and not has_admin:
            admin = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                email=settings.ADMIN_EMAIL,
                real_name="系统管理员",
                role_id=admin_role.id,
            )
            db.add(admin)
            # 不打印密码明文，避免启动日志泄露管理员凭据
            print(f"[启动] 已创建默认管理员: {settings.ADMIN_USERNAME}（密码见 .env 配置）")

        db.commit()

    finally:
        db.close()


def _init_default_videos():
    """
    预置视频专区精选条目
    幂等：仅在 videos 表为空时写入，管理员后续删除/编辑不会被还原
    """
    from app.db.sqlite import SessionLocal
    from app.services.video_seed import seed_default_videos

    db = SessionLocal()
    try:
        created = seed_default_videos(db)
        db.commit()
        if created:
            print(f"[启动] 已预置 {created} 个精选视频（视频专区）")
    except Exception as exc:
        db.rollback()
        print(f"[启动] 视频预置数据初始化失败（不影响服务启动）: {exc}")
    finally:
        db.close()


def _init_crawler_store():
    """
    初始化爬虫子库（独立 SQLite）：建表 + 同步 config/sites.yaml 站点档案。

    交付包默认不包含 backend/crawler/data（爬取运行期数据），缺库时
    「爬取中心」查询会因缺表报 500；此处幂等初始化，保证新环境页面可用。
    """
    try:
        from crawler.store import repo
        from crawler.store.db import init_db as init_crawler_db, session_scope

        init_crawler_db()
        with session_scope() as session:
            repo.sync_sites(session)
        print("[启动] 爬虫子库已就绪")
    except Exception as exc:
        print(f"[启动] 爬虫子库初始化失败（不影响主站问答）: {exc}")
