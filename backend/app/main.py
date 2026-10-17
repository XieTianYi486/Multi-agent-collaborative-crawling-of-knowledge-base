# ============================================================
# FastAPI 应用入口
# 组装路由、中间件、异常处理、生命周期管理
# ============================================================

from contextlib import asynccontextmanager
import os
from pathlib import Path

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

from app.models.user import Role, User
from app.core.security import hash_password

# ==================== 应用生命周期 ====================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    # 启动时
    print(f"[启动] {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"[启动] 初始化数据库...")

    # 创建所有表
    init_db()

    # 初始化默认数据（角色 + 管理员）
    _init_default_data()

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
            Role(name="部门管理员", code="dept_admin",
                 description="管理部门文档和问答统计",
                 permissions=["documents:read", "stats:read"]),
            Role(name="老师", code="teacher",
                 description="教学人员，可查询知识库内容与统计",
                 permissions=["chat:ask", "documents:read", "stats:read"]),
            Role(name="学生", code="student",
                 description="学生，可查询知识库内容",
                 permissions=["chat:ask", "documents:read"]),
            Role(name="普通员工", code="employee",
                 description="查询知识库收录的技术资料",
                 permissions=["chat:ask", "documents:read"]),
        ]

        # 幂等补齐：按 code 插入缺失角色（兼容已有数据库）
        existing_codes = {r.code for r in db.query(Role).all()}
        for role in roles:
            if role.code not in existing_codes:
                db.add(role)
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
            print(f"[启动] 已创建默认管理员: {settings.ADMIN_USERNAME} / {settings.ADMIN_PASSWORD}")

        db.commit()

    finally:
        db.close()
