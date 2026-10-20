# ============================================================
# 向量数据库客户端（支持多种后端）
# 首选 ChromaDB，降级为 FAISS（兼容旧版 Python/SQLite）
# ============================================================

import json
import os
import pickle
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

import numpy as np

from app.core.config import settings


# ==================== 抽象接口 ====================

class BaseVectorStore(ABC):
    """向量存储抽象接口"""

    @abstractmethod
    def add_embeddings(
        self, ids: List[str], embeddings: List[List[float]],
        documents: List[str], metadatas: Optional[List[Dict]] = None,
    ) -> None: ...

    @abstractmethod
    def search(
        self, query_embedding: List[float], top_k: int = 20,
        where: Optional[Dict] = None,
    ) -> Dict: ...

    @abstractmethod
    def delete_by_ids(self, ids: List[str]) -> None: ...

    @abstractmethod
    def delete_by_filter(self, where: Dict) -> None: ...

    @abstractmethod
    def count(self) -> int: ...


# ==================== ChromaDB 实现 ====================

class ChromaVectorStore(BaseVectorStore):
    """ChromaDB 向量存储（推荐）"""

    def __init__(self):
        self._init_chromadb()

    def _init_chromadb(self):
        import chromadb

        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=chromadb.Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        self._collection = self._client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"description": "人工智能学院教学知识库向量库（多智能体爬取入库）"},
        )

    def add_embeddings(self, ids, embeddings, documents, metadatas=None):
        self._collection.add(
            ids=ids, embeddings=embeddings,
            documents=documents,
            metadatas=metadatas or [{} for _ in ids],
        )

    def search(self, query_embedding, top_k=20, where=None):
        raw = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k, where=where,
            include=["documents", "metadatas", "distances"],
        )
        # 统一分数语义：scores 越大越相似（ChromaDB distances 越小越相似）
        raw["scores"] = [
            [1.0 / (1.0 + d) if d else 1.0 for d in dists]
            for dists in raw.get("distances", [[]])
        ]
        return raw

    def delete_by_ids(self, ids):
        if ids:
            self._collection.delete(ids=ids)

    def delete_by_filter(self, where):
        self._collection.delete(where=where)

    def count(self):
        return self._collection.count()


# ==================== FAISS 实现（降级方案）====================

class FaissVectorStore(BaseVectorStore):
    """
    FAISS 向量存储（低内存版，针对 2 核 2G 低配服务器）

    设计要点：
    1. 不再用 Python dict 冗余保存向量（原 _idx_to_emb 占 ~1GB），
       需要向量时用 faiss 的 reconstruct(idx) 从索引直接取回；
    2. chunk 文本(doc)与元数据(meta)持久化到本地 SQLite，
       查询时仅按命中的 idx 批量取出 top_k 条，不整体驻留内存；
    3. 内存常驻仅保留：FAISS 索引本体 + id->idx 小映射（约 3MB）。

    约定：search() 返回的 scores 为"越大越相似"（已映射到 [0,1]），
    与 ChromaVectorStore 的分数语义保持一致。
    """

    def __init__(self):
        self._index = None
        self._dimension = settings.EMBEDDING_DIMENSION
        self._id_to_idx: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._save_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")
        self._conn = None
        self._load_or_create()

    # ---------- SQLite 元数据持久化 ----------

    def _open_meta_db(self) -> sqlite3.Connection:
        os.makedirs(self._save_path, exist_ok=True)
        conn = sqlite3.connect(
            os.path.join(self._save_path, "meta.sqlite3"),
            check_same_thread=False,
        )
        # 与主库保持一致：WAL 模式避免并发读被写锁阻塞
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS chunks (
                idx INTEGER PRIMARY KEY,
                chunk_id TEXT UNIQUE NOT NULL,
                doc TEXT,
                meta TEXT
            )"""
        )
        conn.commit()
        return conn

    def _load_or_create(self):
        os.makedirs(self._save_path, exist_ok=True)
        index_file = os.path.join(self._save_path, "index.faiss")
        sqlite_file = os.path.join(self._save_path, "meta.sqlite3")
        pkl_file = os.path.join(self._save_path, "metadata.pkl")

        if os.path.exists(index_file) and os.path.exists(sqlite_file):
            import faiss
            self._index = faiss.read_index(index_file)
            self._conn = self._open_meta_db()
            self._id_to_idx = {
                row[0]: row[1]
                for row in self._conn.execute("SELECT chunk_id, idx FROM chunks")
            }
        elif os.path.exists(index_file) and os.path.exists(pkl_file):
            # 旧版数据：metadata.pkl -> SQLite 一次性迁移（忽略冗余的 idx_to_emb）
            self._migrate_from_pickle(index_file, pkl_file)
        else:
            self._create_empty_index()

    def _migrate_from_pickle(self, index_file: str, pkl_file: str):
        import faiss
        self._index = faiss.read_index(index_file)
        with open(pkl_file, "rb") as f:
            data = pickle.load(f)
        id_to_idx = data.get("id_to_idx", {})
        idx_to_doc = data.get("idx_to_doc", {})
        idx_to_meta = data.get("idx_to_meta", {})

        self._conn = self._open_meta_db()
        self._conn.execute("DELETE FROM chunks")
        rows = [
            (idx, cid, idx_to_doc.get(idx, ""),
             json.dumps(idx_to_meta.get(idx, {}), ensure_ascii=False))
            for cid, idx in id_to_idx.items()
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO chunks (idx, chunk_id, doc, meta) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        self._id_to_idx = dict(id_to_idx)
        self._save()

    def _create_empty_index(self):
        import faiss
        self._index = faiss.IndexFlatIP(self._dimension)  # 内积相似度
        self._id_to_idx = {}
        self._conn = self._open_meta_db()

    def _save(self):
        import faiss
        faiss.write_index(self._index, os.path.join(self._save_path, "index.faiss"))
        if self._conn is not None:
            self._conn.commit()

    def add_embeddings(self, ids, embeddings, documents, metadatas=None):
        import faiss
        import numpy as np

        vectors = np.array(embeddings, dtype=np.float32)
        # 归一化用于内积=余弦相似度
        faiss.normalize_L2(vectors)

        with self._lock:
            # 幂等：已存在的 chunk_id 先从映射与 SQLite 中清除（旧向量行稍后随重建丢弃）
            has_dup = False
            for cid in ids:
                if cid in self._id_to_idx:
                    old_idx = self._id_to_idx[cid]
                    self._conn.execute("DELETE FROM chunks WHERE idx = ?", (old_idx,))
                    del self._id_to_idx[cid]
                    has_dup = True

            # 追加新向量行
            start_idx = self._index.ntotal
            self._index.add(vectors)

            rows = []
            for i, cid in enumerate(ids):
                idx = start_idx + i
                self._id_to_idx[cid] = idx
                rows.append((
                    idx, cid, documents[i],
                    json.dumps(metadatas[i] if metadatas else {}, ensure_ascii=False),
                ))
            self._conn.executemany(
                "INSERT OR REPLACE INTO chunks (idx, chunk_id, doc, meta) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()

            if has_dup:
                # 存在被替换的旧行时整体重建，避免索引中出现孤儿行
                self._rebuild_index()
            else:
                self._save()

    def search(self, query_embedding, top_k=20, where=None):
        import faiss
        import numpy as np

        vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(vec)

        with self._lock:
            search_k = min(top_k * 3, self._index.ntotal) if where else top_k
            if self._index.ntotal == 0 or search_k == 0:
                return {"ids": [[]], "scores": [[]], "distances": [[]],
                        "documents": [[]], "metadatas": [[]]}

            distances, indices = self._index.search(vec, search_k)

            # 仅按命中的 idx 批量取出 chunk_id/doc/meta（不整体加载）
            hit_idxs = [int(i) for i in indices[0] if i >= 0]
            meta_rows: Dict[int, tuple] = {}
            if hit_idxs:
                ph = ",".join("?" * len(hit_idxs))
                for r in self._conn.execute(
                    f"SELECT idx, chunk_id, doc, meta FROM chunks WHERE idx IN ({ph})",
                    hit_idxs,
                ):
                    meta_rows[int(r[0])] = (r[1], r[2], json.loads(r[3]) if r[3] else {})

            ids_list = []
            docs_list = []
            metas_list = []
            scores_list = []

            for i, idx in enumerate(indices[0]):
                if idx < 0:
                    continue
                row = meta_rows.get(int(idx))
                if row is None:
                    continue
                chunk_id, doc, meta = row

                # 过滤
                if where and not self._match_filter(meta, where):
                    continue

                ids_list.append(chunk_id)
                docs_list.append(doc)
                metas_list.append(meta)
                # 内积相似度映射到 [0,1]（越大越相似）
                ip = float(distances[0][i])
                scores_list.append((ip + 1.0) / 2.0)

                if len(ids_list) >= top_k:
                    break

            return {
                "ids": [ids_list],
                "scores": [scores_list],
                "distances": [scores_list],  # 兼容旧字段名（语义已统一为相似度）
                "documents": [docs_list],
                "metadatas": [metas_list],
            }

    def _match_filter(self, meta: Dict, where: Dict) -> bool:
        if "$and" in where:
            return all(self._match_filter(meta, cond) for cond in where["$and"])
        for key, condition in where.items():
            if key.startswith("$"):
                continue
            meta_val = meta.get(key)
            if isinstance(condition, dict):
                if "$lte" in condition and meta_val > condition["$lte"]:
                    return False
                if "$gte" in condition and meta_val < condition["$gte"]:
                    return False
                if "$in" in condition and meta_val not in condition["$in"]:
                    return False
                if "$ne" in condition and meta_val == condition["$ne"]:
                    return False
            elif meta_val != condition:
                return False
        return True

    def delete_by_ids(self, ids):
        with self._lock:
            removed = False
            for cid in ids:
                if cid in self._id_to_idx:
                    idx = self._id_to_idx[cid]
                    self._conn.execute("DELETE FROM chunks WHERE idx = ?", (idx,))
                    del self._id_to_idx[cid]
                    removed = True
            if removed:
                self._conn.commit()
                self._rebuild_index()

    def delete_by_filter(self, where):
        with self._lock:
            to_remove = []
            for idx, chunk_id, meta_json in self._conn.execute(
                "SELECT idx, chunk_id, meta FROM chunks"
            ):
                meta = json.loads(meta_json) if meta_json else {}
                if self._match_filter(meta, where):
                    to_remove.append((idx, chunk_id))

            if to_remove:
                for idx, chunk_id in to_remove:
                    self._conn.execute("DELETE FROM chunks WHERE idx = ?", (idx,))
                    self._id_to_idx.pop(chunk_id, None)
                self._conn.commit()
                self._rebuild_index()

    def _rebuild_index(self):
        """基于 FAISS 已存向量 reconstruct 重建索引（不再依赖冗余副本）"""
        import faiss
        import numpy as np

        rows = list(self._conn.execute(
            "SELECT idx, chunk_id, doc, meta FROM chunks ORDER BY idx"
        ))

        new_index = faiss.IndexFlatIP(self._dimension)
        new_id_to_idx: Dict[str, int] = {}
        new_rows = []

        for old_idx, chunk_id, doc, meta_json in rows:
            vec = self._index.reconstruct(int(old_idx))  # 已归一化的 float32 向量
            new_idx = new_index.ntotal
            new_index.add(np.ascontiguousarray(vec, dtype=np.float32).reshape(1, -1))
            new_id_to_idx[chunk_id] = new_idx
            new_rows.append((new_idx, chunk_id, doc, meta_json))

        self._index = new_index
        self._id_to_idx = new_id_to_idx
        self._conn.execute("DELETE FROM chunks")
        self._conn.executemany(
            "INSERT OR REPLACE INTO chunks (idx, chunk_id, doc, meta) "
            "VALUES (?, ?, ?, ?)",
            new_rows,
        )
        self._conn.commit()
        self._save()

    def count(self):
        return self._index.ntotal


# ==================== 工厂函数 ====================

_vector_store: Optional[BaseVectorStore] = None


def get_vector_store() -> BaseVectorStore:
    """获取向量存储实例（按 VECTOR_BACKEND 配置选择后端）"""
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    backend = settings.VECTOR_BACKEND.lower()

    # 强制 FAISS（低内存后端，2 核 2G 低配服务器场景）
    if backend == "faiss":
        _vector_store = FaissVectorStore()
        return _vector_store

    # 强制 ChromaDB
    if backend == "chroma":
        _vector_store = ChromaVectorStore()
        return _vector_store

    # auto：优先 ChromaDB（sqlite3>=3.35），失败则降级 FAISS
    try:
        import sqlite3
        if sqlite3.sqlite_version_info >= (3, 35, 0):
            _vector_store = ChromaVectorStore()
            return _vector_store
    except Exception:
        pass

    _vector_store = FaissVectorStore()
    return _vector_store
