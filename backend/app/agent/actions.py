# ============================================================
# 写操作确认令牌
#
# 模型不能直接执行有副作用的工具：Agent 只生成一个短时令牌返回给前端，
# 用户点击"确认"后由 /counselor/actions/confirm 携带令牌调用本模块校验，
# 校验通过才真正执行工具。
#
# 令牌使用项目既有 JWT 密钥签名，绑定用户、工具名与参数，5 分钟过期；
# 已消费的 jti 记录在进程内，防止同一确认被重复提交（幂等）。
# ============================================================

import threading
import time
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from app.core.exceptions import ValidationException
from app.agent.registry import ToolContext

# 说明：jose / cryptography 采用函数内延迟导入。
# 一是不让"只是导入 Agent 模块"的脚本被动加载加密库，
# 二是规避部分 Windows Python 环境下与 FastAPI/OpenSSL 的 DLL 加载顺序冲突。

ACTION_TTL_SECONDS = 300
_TOKEN_TYPE = "agent_action"

_consumed: Dict[str, float] = {}
_lock = threading.Lock()


def create_action_token(
    ctx: ToolContext,
    tool_name: str,
    args: Dict[str, Any],
    session_id: Optional[str] = None,
) -> str:
    """为一次写操作生成待确认令牌"""
    from app.core.security import create_access_token

    return create_access_token(
        subject=str(ctx.user_id),
        extra_claims={
            "typ": _TOKEN_TYPE,
            "tool": tool_name,
            "args": args,
            "sid": session_id or "",
            "jti": uuid.uuid4().hex,
        },
        expires_delta=timedelta(seconds=ACTION_TTL_SECONDS),
    )


def consume_action_token(token: str) -> Dict[str, Any]:
    """
    校验并消费确认令牌，返回 payload。

    校验项：签名/过期、令牌类型、jti 未被消费。
    用户归属与角色在调用方再次校验，避免令牌被他人复用。
    """
    from jose import JWTError

    from app.core.security import decode_access_token

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise ValidationException("操作确认已过期，请重新发起")

    if payload.get("typ") != _TOKEN_TYPE:
        raise ValidationException("无效的操作确认")

    jti = payload.get("jti") or ""
    if not jti:
        raise ValidationException("无效的操作确认")

    now = time.time()
    with _lock:
        # 顺便清理已过期记录，避免进程长期运行后无限增长
        for key, exp in list(_consumed.items()):
            if exp <= now:
                _consumed.pop(key, None)
        if jti in _consumed:
            raise ValidationException("该操作已执行，请勿重复提交")
        _consumed[jti] = float(payload.get("exp") or (now + ACTION_TTL_SECONDS))

    return payload
