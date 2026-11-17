# ============================================================
# 通用文本嵌入封装（DashScope / DeepSeek 远程 API + ONNX 本地模型）
# 通过 EMBEDDING_PROVIDER 切换: dashscope / deepseek / onnx_bge
# ============================================================

import os
import time
from typing import List, Optional

import numpy as np
from app.core.config import settings
from app.core.exceptions import EmbeddingException

# BGE 中文检索在查询侧建议添加的指令前缀（文档侧不加）
_BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


# ---------- 远程 API 配置 ----------
_PROVIDER_DEFAULTS = {
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "text-embedding-v2",
        "supports_text_type": True,
        "dim": 1536,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-embedding-v1",
        "supports_text_type": False,
        "dim": 1536,
    },
    "onnx_bge": {
        # 本地 BGE-small-zh-v1.5 ONNX，512 维
        "model": "bge-small-zh-v1.5",
        "dim": 512,
    },
}


class TextEmbeddings:
    """
    通用文本嵌入服务

    通过 EMBEDDING_PROVIDER 切换:
      - dashscope:   阿里云百炼 text-embedding-v2 (1536 维, 远程 API)
      - deepseek:    DeepSeek (远程 API, 注意: 官方不提供公开 embedding endpoint)
      - onnx_bge:    本地 BGE-small-zh-v1.5 ONNX (512 维, 零成本零依赖)
    """

    def __init__(self):
        self.provider = (settings.EMBEDDING_PROVIDER or "dashscope").lower()
        defaults = _PROVIDER_DEFAULTS.get(self.provider, _PROVIDER_DEFAULTS["dashscope"])
        self.dimension = settings.EMBEDDING_DIMENSION or defaults.get("dim", 512)
        self.model = settings.EMBEDDING_MODEL or defaults.get("model", "")

        self._local = self.provider in ("onnx_bge", "local")

        if self._local:
            self._init_local_onnx()
        else:
            self._init_remote_api(defaults)

    # ---------------- 本地 ONNX 初始化 ----------------
    def _init_local_onnx(self):
        """加载本地 ONNX 模型 + tokenizer"""
        import onnxruntime as ort
        from transformers import AutoTokenizer

        model_dir = (settings.EMBEDDING_LOCAL_MODEL or
                     os.path.join(settings.CHROMA_PERSIST_DIR, "models", "bge-small-zh-onnx"))
        onnx_path = os.path.join(model_dir, "model.onnx")
        if not os.path.exists(onnx_path):
            raise EmbeddingException(
                f"本地 ONNX 模型不存在: {onnx_path}\n"
                f"请设置 EMBEDDING_LOCAL_MODEL 指向正确目录"
            )

        print(f"[Embedding] 加载本地 ONNX: {onnx_path}")
        # 多线程加速：全量重建 23k 分块时 4 线程约为单线程的 3 倍
        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = min(4, os.cpu_count() or 1)
        sess_opts.inter_op_num_threads = 1
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self._sess = ort.InferenceSession(
            onnx_path, sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )
        # 不同导出的 ONNX 输入集合不同：有的必须传 token_type_ids，且要求 int64
        self._input_names = {i.name for i in self._sess.get_inputs()}
        self._tok = AutoTokenizer.from_pretrained(model_dir)
        self._model_dir = model_dir
        print(f"[Embedding] provider=onnx_bge, model={self.model}, dim={self.dimension}")

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """本地 ONNX 推理 + mean pooling + L2 normalize
        按小 batch 分批推理，控制 BERT 注意力中间张量的内存峰值
        """
        all_results = []
        # 小 batch（BERT-base 在 seq_len=512 时 batch=4 内存峰值约 300MB）
        MICRO_BATCH = 4
        # 与 CHUNK_SIZE=512 对齐：256 会截掉一半分块内容，直接损伤召回
        MAX_LEN = 512
        for i in range(0, len(texts), MICRO_BATCH):
            batch = texts[i:i + MICRO_BATCH]
            enc = self._tok(
                batch, padding=True, truncation=True,
                max_length=MAX_LEN, return_tensors="np"
            )
            feed = {
                "input_ids": enc["input_ids"].astype(np.int64),
                "attention_mask": enc["attention_mask"].astype(np.int64),
            }
            if "token_type_ids" in self._input_names:
                feed["token_type_ids"] = enc.get(
                    "token_type_ids", np.zeros_like(enc["input_ids"])
                ).astype(np.int64)
            outs = self._sess.run(None, feed)
            last_hidden = outs[0]  # (batch, seq_len, hidden)
            # BGE 系列必须用 CLS 池化（首 token），mean pooling 会显著损伤检索区分度
            pooled = last_hidden[:, 0]
            norms = np.linalg.norm(pooled, axis=1, keepdims=True) + 1e-12
            result = (pooled / norms).astype(np.float32)
            all_results.extend(result.tolist())
            del enc, outs, last_hidden, pooled, norms, result
        return all_results

    # ---------------- 远程 API 初始化 ----------------
    def _init_remote_api(self, defaults: dict):
        import httpx  # 延迟 import，避免本地模式也依赖 httpx

        api_key = settings.EMBEDDING_API_KEY or settings.DASHSCOPE_API_KEY
        if not api_key:
            raise EmbeddingException(f"未配置 Embedding API Key (provider={self.provider})")
        self.api_key = api_key
        self.base_url = (settings.EMBEDDING_BASE_URL or defaults["base_url"]).rstrip("/")
        self._supports_text_type = defaults.get("supports_text_type", False)
        self._httpx = httpx.Client(timeout=60.0)
        print(f"[Embedding] provider={self.provider}, model={self.model}, "
              f"base_url={self.base_url}, dim={self.dimension}")

    def _call_api(self, inputs: List[str], text_type: str = "query") -> List[List[float]]:
        body = {"model": self.model, "input": inputs}
        if self._supports_text_type and text_type:
            body["text_type"] = text_type

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._httpx.post(f"{self.base_url}/embeddings", json=body, headers=headers)
            if resp.status_code != 200:
                raise EmbeddingException(
                    f"Embedding API ({self.provider}) 返回 {resp.status_code}: {resp.text[:300]}"
                )
            return [item["embedding"] for item in resp.json()["data"]]
        except EmbeddingException:
            raise
        except Exception as e:
            raise EmbeddingException(f"Embedding API 网络错误: {e}")

    # ---------------- 公共接口 ----------------
    def embed_query(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.dimension
        texts = [text.strip()]
        if self._local:
            # BGE 中文检索建议查询侧加指令前缀（文档侧不加）
            if "bge" in (self.model or "").lower():
                texts = [f"{_BGE_QUERY_INSTRUCTION}{texts[0]}"]
            return self._embed_local(texts)[0]
        return self._call_api(texts, text_type="query")[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        texts = [t.strip() if t and t.strip() else " " for t in texts]
        if self._local:
            return self._embed_local(texts)  # ONNX 一次跑全部，分批没必要
        # 远程 API 分批（DashScope 单次限 25）
        all_emb, batch = [], 20
        for i in range(0, len(texts), batch):
            all_emb.extend(self._call_api(texts[i:i + batch], text_type="document"))
            if i + batch < len(texts):
                time.sleep(0.1)
        return all_emb


# --- 全局单例 ---
_embeddings_instance: Optional[TextEmbeddings] = None


def get_embeddings() -> TextEmbeddings:
    """获取嵌入服务单例"""
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = TextEmbeddings()
    return _embeddings_instance