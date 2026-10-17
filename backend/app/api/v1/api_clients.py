# ============================================================
# 开放 API 调用方管理接口（仅超级管理员）
# POST   /api/v1/api-clients        创建调用方（明文 Key 仅返回一次）
# GET    /api/v1/api-clients        列表
# PATCH  /api/v1/api-clients/{id}   启停 / 改备注 / 改密级
# ============================================================

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_super_admin
from app.core.security import generate_api_key, hash_api_key
from app.db.sqlite import get_db
from app.models.api_client import ApiClient
from app.models.user import User
from app.schemas.common import APIResponse

router = APIRouter(prefix="/api-clients", tags=["开放API调用方"])


class ApiClientCreate(BaseModel):
    """创建调用方请求"""
    name: str = Field(..., min_length=1, max_length=128, description="调用方名称")
    description: Optional[str] = Field(default=None, max_length=255, description="用途备注")
    security_level: int = Field(default=1, ge=1, le=4, description="可访问密级上限")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间（不填=永不过期）")


class ApiClientUpdate(BaseModel):
    """更新调用方请求（仅传需要修改的字段）"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=255)
    security_level: Optional[int] = Field(default=None, ge=1, le=4)
    status: Optional[int] = Field(default=None, ge=0, le=1, description="0=禁用, 1=启用")


def _serialize(client: ApiClient) -> dict:
    """统一序列化（绝不返回 key_hash）"""
    return {
        "id": client.id,
        "name": client.name,
        "description": client.description,
        "status": client.status,
        "security_level": client.security_level,
        "call_count": client.call_count,
        "last_used_at": client.last_used_at.isoformat() if client.last_used_at else None,
        "expires_at": client.expires_at.isoformat() if client.expires_at else None,
        "created_at": client.created_at.isoformat() if client.created_at else None,
    }


@router.post("", response_model=APIResponse, summary="创建调用方")
def create_api_client(
    request: ApiClientCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """
    创建对外开放调用方

    返回的 api_key 为明文，仅此一次返回，请自行妥善保存；
    数据库只保存其 SHA-256 哈希，遗失后只能重建。
    """
    raw_key = generate_api_key()
    client = ApiClient(
        name=request.name,
        key_hash=hash_api_key(raw_key),
        description=request.description,
        security_level=request.security_level,
        expires_at=request.expires_at,
    )
    db.add(client)
    db.flush()

    data = _serialize(client)
    data["api_key"] = raw_key
    return APIResponse(code=0, message="调用方创建成功", data=data)


@router.get("", response_model=APIResponse, summary="调用方列表")
def list_api_clients(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    clients = db.query(ApiClient).order_by(ApiClient.id.desc()).all()
    return APIResponse(code=0, message="success", data=[_serialize(c) for c in clients])


@router.patch("/{client_id}", response_model=APIResponse, summary="更新调用方")
def update_api_client(
    client_id: int,
    request: ApiClientUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    client = db.query(ApiClient).filter(ApiClient.id == client_id).first()
    if client is None:
        return APIResponse(code=3001, message="调用方不存在")

    if request.name is not None:
        client.name = request.name
    if request.description is not None:
        client.description = request.description
    if request.security_level is not None:
        client.security_level = request.security_level
    if request.status is not None:
        client.status = request.status

    db.flush()
    return APIResponse(code=0, message="更新成功", data=_serialize(client))