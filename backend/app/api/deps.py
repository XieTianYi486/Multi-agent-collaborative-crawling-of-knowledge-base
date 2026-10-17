# ============================================================
# FastAPI 依赖注入
# JWT 认证、用户获取、权限校验
# ============================================================

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_token_payload, hash_api_key
from app.db.sqlite import get_db, SessionLocal
from app.models.api_client import ApiClient
from app.models.user import User, Role

# --- Bearer Token 认证方案 ---
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    """
    从 JWT Token 获取当前登录用户
    所有受保护接口的基础依赖

    使用独立的短生命周期 Session 加载用户，加载完成后立即 expunge，
    返回一个 detached 但数据已完全加载的 User 对象。
    这样即使用户请求的主 Session 发生 rollback（会无条件 expire 所有对象），
    也不会影响 current_user，彻底避免 "not bound to a Session" 错误。

    返回:
        当前登录的 User 对象（detached，role 已预加载）

    异常:
        401: Token 缺失或无效
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )

    token = credentials.credentials
    payload = get_token_payload(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新登录",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 格式无效",
        )

    # --- 使用独立 Session 加载用户 ---
    # 这个 Session 仅用于加载 User 及其 role，加载完成后立即关闭，
    # User 对象通过 expunge 脱离 Session，不受后续主 Session 的任何影响
    user_db = SessionLocal()
    try:
        user = (
            user_db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == int(user_id))
            .first()
        )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
            )

        if user.status == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被禁用，请联系管理员",
            )

        # 强制访问 role 属性，确保 joinedload 的数据已加载到内存
        # （正常情况下 joinedload 已保证，此处是额外的安全保障）
        _ = user.role

        # 将 User 从当前 Session 中 expunge（脱离），
        # 使其成为 detached 对象。所有已加载的属性保持在内存中，
        # 访问时不会触发数据库查询
        user_db.expunge(user)

        return user

    finally:
        user_db.close()


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前活跃用户（status=1）"""
    return current_user


def require_role(role_codes: list[str]):
    """
    角色权限校验工厂函数

    current_user 是 detached 对象（已在 get_current_user 中 expunge），
    但 role 已通过 joinedload 预加载到内存，访问 user.role 不会触发数据库查询。

    使用方式:
        @router.get("/admin/users")
        def admin_endpoint(user = Depends(require_role(["super_admin"]))):
            ...
    """

    def checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        # role 已通过 joinedload 预加载，无需数据库查询
        if current_user.role is None or current_user.role.code not in role_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，无法执行此操作",
            )
        return current_user

    return checker


# --- 预设的角色检查器 ---
require_super_admin = require_role(["super_admin"])
require_knowledge_admin = require_role(["super_admin", "knowledge_admin"])
require_dept_admin = require_role(["super_admin", "knowledge_admin", "dept_admin"])


# ==================== 开放 API 鉴权 ====================

def get_api_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> ApiClient:
    """
    从 Authorization: Bearer <API Key> 解析开放 API 调用方

    与用户 JWT 分离：这里校验的是长期应用凭证（api_clients 表），
    不涉及 RBAC 角色，可访问的密级上限由 client.security_level 决定。

    返回:
        ApiClient 对象（detached，可直接读取全部字段）

    异常:
        401: 未提供 API Key 或 Key 无效
        403: Key 已被禁用或已过期
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 API Key，请通过 Authorization: Bearer <API Key> 提供",
        )

    key_hash = hash_api_key(credentials.credentials)
    db = SessionLocal()
    try:
        client = (
            db.query(ApiClient)
            .filter(ApiClient.key_hash == key_hash)
            .first()
        )

        if client is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key 无效",
            )

        if client.status != 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="该 API Key 已被禁用",
            )

        if client.expires_at is not None:
            # SQLite 取回的 DATETIME 不带时区，补成 UTC 后再比较
            expires_at = client.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="该 API Key 已过期",
                )

        # 累计调用次数与最近调用时间
        client.call_count = (client.call_count or 0) + 1
        client.last_used_at = datetime.now(timezone.utc)
        db.commit()

        db.expunge(client)
        return client

    finally:
        db.close()
