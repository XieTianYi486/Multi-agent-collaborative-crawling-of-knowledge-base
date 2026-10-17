# ============================================================
# 对外开放 API v1
# POST /openapi/v1/search  - 知识片段检索（不调用 LLM）
# POST /openapi/v1/ask     - 知识库问答（完整 RAG）
#
# 鉴权：Authorization: Bearer <API Key>（应用凭证，非用户 JWT）
# 密级：由调用方凭证的 security_level 决定可访问范围
# ============================================================

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_api_client
from app.models.api_client import ApiClient
from app.schemas.common import APIResponse
from app.schemas.openapi import OpenAskRequest, OpenSearchRequest
from app.services.chat_service import get_chat_service

router = APIRouter(prefix="/v1", tags=["开放 API"])
logger = logging.getLogger(__name__)


@router.post("/search", response_model=APIResponse, summary="知识片段检索")
def open_search(
    request: OpenSearchRequest,
    client: ApiClient = Depends(get_api_client),
):
    """
    混合检索接口（不调用 LLM）

    返回经发布/审核/密级过滤后的知识片段列表，调用方自行组装上下文。
    """
    chunks = get_chat_service().search_chunks(
        query=request.query,
        security_level=client.security_level,
        top_k=request.top_k,
    )

    results = [
        {
            "chunk_id": c.get("chunk_id", ""),
            "document_id": c.get("document_id", 0),
            "document_name": c.get("document_name", ""),
            "chapter": c.get("chapter", ""),
            "page": c.get("page", 1),
            "content": c.get("content", ""),
            "score": round(c.get("score", 0), 4),
            "source_url": c.get("source_url", ""),
        }
        for c in chunks
    ]

    return APIResponse(
        code=0,
        message="success",
        data={"query": request.query, "total": len(results), "results": results},
    )


@router.post("/ask", response_model=APIResponse, summary="知识库问答")
def open_ask(
    request: OpenAskRequest,
    client: ApiClient = Depends(get_api_client),
):
    """
    知识库问答接口（完整 RAG：检索 → 重排 → LLM 生成）

    调用方凭证的密级决定可引用的文档范围。
    """
    result = get_chat_service().ask(
        question=request.question,
        security_level=client.security_level,
    )

    return APIResponse(
        code=0,
        message="success",
        data={
            "question": request.question,
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "usage": result.get("usage", {}),
            "latency": result.get("latency", {}),
        },
    )