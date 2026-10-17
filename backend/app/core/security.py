# ============================================================
# 安全模块 —— JWT Token 生成与验证、密码哈希
# 使用 python-jose + passlib
# ============================================================

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# --- 密码哈希上下文 ---
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # 适当的加密轮数
)

# --- 算法常量 ---
ALGORITHM = settings.JWT_ALGORITHM
SECRET_KEY = settings.JWT_SECRET_KEY


# ==================== 密码工具函数 ====================

def hash_password(plain_password: str) -> str:
    """对明文密码进行 bcrypt 哈希"""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


# ==================== 开放 API Key 工具函数 ====================

def generate_api_key() -> str:
    """生成对外开放 API Key（格式：kb_ + 32 位十六进制，128 位随机）"""
    return "kb_" + secrets.token_hex(16)


def hash_api_key(raw_key: str) -> str:
    """
    API Key 单向哈希（SHA-256）

    Key 本身是 128 位随机串，熵足够高，不存在被字典穷举的风险，
    因此用快速哈希而非 bcrypt：既可按唯一索引定值查找，
    也避免每次外部调用都付出一次慢哈希校验的时延。
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# ==================== JWT Token 工具函数 ====================

def create_access_token(
    subject: str,
    extra_claims: Optional[dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建 JWT Access Token

    参数:
        subject: Token 主体（通常是用户 ID）
        extra_claims: 额外声明（如用户名、角色等）
        expires_delta: 过期时间差，为 None 则使用默认配置

    返回:
        编码后的 JWT 字符串
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    # 标准 JWT claims
    claims = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
    }

    # 合并额外声明（如 username, role 等）
    if extra_claims:
        claims.update(extra_claims)

    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    解码 JWT Token 并返回其中的声明

    参数:
        token: JWT 字符串

    返回:
        解码后的 claims 字典

    异常:
        JWTError: Token 无效或已过期
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_token_payload(token: str) -> Optional[dict[str, Any]]:
    """
    安全地解码 Token，失败时返回 None（不抛异常）

    参数:
        token: JWT 字符串

    返回:
        claims 字典 或 None
    """
    try:
        return decode_access_token(token)
    except JWTError:
        return None
