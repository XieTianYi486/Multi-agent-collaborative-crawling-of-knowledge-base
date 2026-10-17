# ============================================================
# 百炼 Embedding 封装（OpenAI 兼容模式）
# 使用 HTTP API 直接调用，避免 DashScope SDK 兼容性问题
# ============================================================

import time
from typing import List, Optional

import httpx

from app.core.config import settings
from app.core.exceptions import EmbeddingException


class DashScopeEmbeddings:
    """
    百炼文本嵌入服务

    使用 OpenAI 兼容 HTTP API：
    POST {base_url}/embeddings
    """

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION

        # 使用 MaaS 工作空间 OpenAI 兼容端点
        self.base_url = (
            settings.DASHSCOPE_OPENAI_BASE_URL or
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")

        if not self.api_key:
            raise EmbeddingException("未配置 DASHSCOPE_API_KEY")

    def _call_api(self, inputs: List[str], text_type: str = "query") -> List[List[float]]:
        """
        调用 Embedding API

        参数:
            inputs: 文本列表
            text_type: "query" 或 "document"

        返回:
            向量列表
        """
        url = f"{self.base_url}/embeddings"

        body = {
            "model": self.model,
            "input": inputs,
        }

        # 某些 endpoint 支持 text_type 参数优化检索
        if text_type:
            body["text_type"] = text_type

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=body, headers=headers)

            if resp.status_code != 200:
                error_msg = resp.text[:500]
                raise EmbeddingException(
                    f"Embedding API 返回错误 ({resp.status_code}): {error_msg}"
                )

            data = resp.json()
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings

        except httpx.RequestError as e:
            raise EmbeddingException(f"Embedding API 网络请求失败: {str(e)}")

    def embed_query(self, text: str) -> List[float]:
        """对查询文本进行向量化"""
        if not text or not text.strip():
            return [0.0] * self.dimension

        result = self._call_api([text.strip()], text_type="query")
        return result[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量对文档文本进行向量化
        百炼 API 单次调用最多支持 25 条
        """
        if not texts:
            return []

        all_embeddings = []
        batch_size = 20  # 每批 20 条，留余量

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch = [t.strip() if t and t.strip() else " " for t in batch]

            batch_embeddings = self._call_api(batch, text_type="document")
            all_embeddings.extend(batch_embeddings)

            # 速率限制
            if i + batch_size < len(texts):
                time.sleep(0.1)

        return all_embeddings


# --- 全局单例 ---
_embeddings_instance: Optional[DashScopeEmbeddings] = None


def get_embeddings() -> DashScopeEmbeddings:
    """获取嵌入服务单例"""
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = DashScopeEmbeddings()
    return _embeddings_instance
