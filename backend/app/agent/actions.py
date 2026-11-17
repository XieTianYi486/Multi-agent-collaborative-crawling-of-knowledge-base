# ============================================================
# 写操作确认令牌（服务端状态 + 短时 JWT 引用）
#
# 模型只能"提议"有副作用的工具：Agent 生成一个短时令牌返回给前端，
# 用户点击"确认"后由 /counselor/actions/confirm 携带令牌调用本模块校验，
# 校验通过才真正执行工具。
#
# 设计要点：
# - JWT 里只放 {sub, jti, typ}，工具名与参数存数据库
#   （jose 会把中文转 \uXXXX 转义，参数进 JWT 会让 token 超长，
#    500 字中文问题的确认卡会超过接口 4000 字符上限永远无法提交）；
# - 一次性消费由数据库行原子更新保证（UPDATE ... WHERE consumed_at IS NULL），
#   跨进程、跨重启、多 worker 均有效，不依赖进程内存；
# - 用户归属与角色由调用方基于登录态再次校验，令牌本身不做授权。
# ============================================================

import json
import uuid
from datetime import timedelta, timezone
from typing import Any, Dict, Optional

from app.core.exceptions import ValidationException
from app.core.security import create_access_token
from app.db.sqlite import SessionLocal
from app.models.agent_action import AgentActionToken
from app.models.user import utcnow

ACTION_TTL_SECONDS = 300
_TOKEN_TYPE = "agent_action"


def create_action_token(
    ctx,
    tool_name: str,
    args: Dict[str, Any],
    session_id: Optional[str] = None,
) -> str:
    """
    为一次写操作生成待确认令牌。

    参数与服务端状态先落库，JWT 只携带 jti 引用。
    返回的 token 与调用方之间只通过 jti 关联，参数不可被篡改。
    """
    jti = uuid.uuid4().hex
    expires_at = utcnow() + timedelta(seconds=ACTION_TTL_SECONDS)

    db = SessionLocal()
    try:
        _purge_expired(db)
        db.add(AgentActionToken(
            jti=jti,
            user_id=ctx.user_id,
            tool=tool_name,
            args_json=json.dumps(args or {}, ensure_ascii=False),
            session_id=session_id or None,
            expires_at=expires_at,
        ))
        db.commit()
    finally:
        db.close()

    return create_access_token(
        subject=str(ctx.user_id),
        extra_claims={
            "typ": _TOKEN_TYPE,
            "jti": jti,
        },
        expires_delta=timedelta(seconds=ACTION_TTL_SECONDS),
    )


def consume_action_token(
    token: str,
    expected_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    校验并消费确认令牌，返回 payload：
    {"sub", "tool", "args", "sid", "jti"}。

    校验项：签名/过期、令牌类型、jti 存在且未被消费；
    expected_user_id 传入时先校验归属再消费（避免他人令牌被烧毁）。
    角色与工具合法性仍由调用方基于登录态二次校验。
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

    db = SessionLocal()
    try:
        row = db.query(AgentActionToken).filter(
            AgentActionToken.jti == jti
        ).first()
        if row is None:
            raise ValidationException("操作确认已过期，请重新发起")

        if expected_user_id is not None and str(row.user_id) != str(expected_user_id):
            raise ValidationException("无权执行该操作")

        now = utcnow()
        # SQLite 落库时丢失时区信息（aware → naive），比较前统一补回 UTC
        expires_at = (
            row.expires_at.replace(tzinfo=timezone.utc)
            if row.expires_at is not None else None
        )
        if row.consumed_at is not None:
            raise ValidationException("该操作已执行，请勿重复提交")
        if expires_at is not None and expires_at < now:
            raise ValidationException("操作确认已过期，请重新发起")

        # 原子消费：只有把 consumed_at 从 NULL 置为当前时间的这一次会成功
        consumed = (
            db.query(AgentActionToken)
            .filter(
                AgentActionToken.jti == jti,
                AgentActionToken.consumed_at.is_(None),
            )
            .update({"consumed_at": now}, synchronize_session=False)
        )
        db.commit()
        if consumed != 1:
            raise ValidationException("该操作已执行，请勿重复提交")

        return {
            "sub": str(row.user_id),
            "tool": row.tool,
            "args": json.loads(row.args_json or "{}"),
            "sid": row.session_id or "",
            "jti": jti,
        }
    except ValidationException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _purge_expired(db) -> None:
    """清理过期/已消费超过一天的令牌行，避免表无限增长。"""
    from sqlalchemy import or_

    # 库内 datetime 为 naive（SQLite 无时区），比较参数也要用 naive UTC
    cutoff = (utcnow() - timedelta(days=1)).replace(tzinfo=None)
    db.query(AgentActionToken).filter(
        or_(
            AgentActionToken.expires_at < cutoff,
            AgentActionToken.consumed_at < cutoff,
        )
    ).delete(synchronize_session=False)
