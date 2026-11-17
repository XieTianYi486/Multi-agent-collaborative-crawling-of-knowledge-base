# ============================================================
# 本地 ONNX 重排序器（BGE-reranker-base int8）
# 用 cross-encoder 对「问题-片段」逐对打分并排序，
# 替代本地 7B LLM 排序：延迟从数秒降到亚秒级，且分数绝对值可做拒答门限。
# ============================================================

import logging
import os
import threading
from typing import Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_LEN = 384          # cross-encoder 输入上限（片段正文较长，384 已覆盖关键段）
_MICRO_BATCH = 4        # 小 batch 控制 CPU 内存峰值


class OnnxReranker:
    """基于 BGE-reranker-base ONNX 的本地重排序器"""

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = (
            model_dir
            or settings.RERANK_LOCAL_MODEL
            or os.path.join(
                settings.CHROMA_PERSIST_DIR, "models", "bge-reranker-base-onnx"
            )
        )
        self._lock = threading.Lock()
        self._sess = None
        self._tok = None
        self._input_names = set()

    def _ensure_loaded(self):
        if self._sess is not None:
            return
        with self._lock:
            if self._sess is not None:
                return
            import onnxruntime as ort
            from transformers import AutoTokenizer

            model_path = os.path.join(self.model_dir, "model.onnx")
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"本地重排模型不存在: {model_path}")

            sess_opts = ort.SessionOptions()
            # 多线程加速：10 个候选的长片段单线程约 3s，4 线程约 1s 内
            sess_opts.intra_op_num_threads = min(4, os.cpu_count() or 1)
            sess_opts.inter_op_num_threads = 1
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            self._sess = ort.InferenceSession(
                model_path, sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )
            self._input_names = {i.name for i in self._sess.get_inputs()}
            self._tok = AutoTokenizer.from_pretrained(self.model_dir)
            logger.info("[Rerank] 加载本地 ONNX: %s", model_path)

    def rerank(self, question: str, candidates: List[Dict]) -> List[Dict]:
        """
        对候选分块按相关性重排。

        返回新列表（不修改入参），每项附带 rerank_score ∈ [0,1]，
        供上层做低相关拒答；模型不可用时回退原顺序。
        """
        if len(candidates) <= 1:
            return candidates

        try:
            self._ensure_loaded()
            import numpy as np

            scores: List[float] = []
            for i in range(0, len(candidates), _MICRO_BATCH):
                group = candidates[i:i + _MICRO_BATCH]
                texts = [(c.get("content") or "") for c in group]
                enc = self._tok(
                    [question] * len(texts), texts,
                    padding=True, truncation=True,
                    max_length=_MAX_LEN, return_tensors="np",
                )
                feed = {
                    "input_ids": enc["input_ids"].astype(np.int64),
                    "attention_mask": enc["attention_mask"].astype(np.int64),
                }
                if "token_type_ids" in self._input_names:
                    feed["token_type_ids"] = enc.get(
                        "token_type_ids", np.zeros_like(enc["input_ids"])
                    ).astype(np.int64)
                logits = self._sess.run(None, feed)[0]
                logits = logits[:, 0] if logits.ndim > 1 else logits
                scores.extend((1.0 / (1.0 + np.exp(-logits))).tolist())

            ranked = []
            for c, s in zip(candidates, scores):
                item = dict(c)
                item["rerank_score"] = float(s)
                ranked.append(item)
            ranked.sort(key=lambda x: x["rerank_score"], reverse=True)
            return ranked

        except Exception as e:
            logger.warning("本地 ONNX 重排序失败，回退到原顺序: %s", e)
            return candidates


# --- 全局单例 ---
_reranker: Optional[OnnxReranker] = None


def get_onnx_reranker() -> OnnxReranker:
    global _reranker
    if _reranker is None:
        _reranker = OnnxReranker()
    return _reranker
