"""向量数据库查看工具（轻量，独立于后端服务）。

功能：
  python inspect_vectors.py                  # 交互模式（无参数）
  python inspect_vectors.py --stats          # 向量库总览
  python inspect_vectors.py --search 关键词  # 按 chunk 文本搜索，查看对应向量
  python inspect_vectors.py --chunk doc_123_chunk_0   # 按 chroma_id 查看
  python inspect_vectors.py --index 42       # 按 FAISS 行号查看
  python inspect_vectors.py --query "查询文本"  # 演示检索：query 向量 vs 库内 top3（有 API 费用）

注意：metadata.pkl 约 335MB，全量加载需 ~1GB 内存；内存不足时自动降级为
"仅 FAISS 数值模式"（只能按行号查看向量数值，无文本映射）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402

from app.core.config import settings  # noqa: E402

INDEX_FILE = Path(settings.CHROMA_PERSIST_DIR) / "faiss_index" / "index.faiss"
META_FILE = Path(settings.CHROMA_PERSIST_DIR) / "faiss_index" / "metadata.pkl"


def vec_summary(vec: np.ndarray, top_n: int = 8) -> str:
    """向量摘要：前 top_n 维数值 + 统计。"""
    parts = [f"维度 {len(vec)}"]
    parts.append("前%d维: [%s ...]" % (top_n, ", ".join(f"{v:.5f}" for v in vec[:top_n])))
    parts.append(f"均值 {vec.mean():.5f} | L2范数 {np.linalg.norm(vec):.4f} | "
                 f"min {vec.min():.5f} | max {vec.max():.5f}")
    return "\n  ".join(parts)


class VectorInspector:
    """加载向量库；内存不足时降级为仅索引数值模式。"""

    def __init__(self):
        import faiss

        self.faiss = faiss
        self.index = faiss.read_index(str(INDEX_FILE))
        self.id_to_idx: dict[str, int] = {}
        self.idx_to_doc: dict[int, str] = {}
        self.idx_to_meta: dict[int, dict] = {}
        self.full_mode = False
        try:
            import pickle
            with open(META_FILE, "rb") as f:
                data = pickle.load(f)
            self.id_to_idx = data.get("id_to_idx", {})
            self.idx_to_doc = data.get("idx_to_doc", {})
            self.idx_to_meta = data.get("idx_to_meta", {})
            self.full_mode = True
        except MemoryError:
            print("[警告] 内存不足，metadata.pkl 加载失败 → 降级为仅 FAISS 数值模式")
        except Exception as exc:  # noqa: BLE001
            print(f"[警告] metadata 加载失败: {exc} → 降级为仅 FAISS 数值模式")

    def stats(self) -> None:
        print("=" * 60)
        print("向量数据库总览")
        print("=" * 60)
        print(f"索引文件: {INDEX_FILE.name} ({INDEX_FILE.stat().st_size / 1e6:.1f} MB)")
        print(f"向量总数: {self.index.ntotal}")
        print(f"向量维度: {self.index.d}")
        print(f"索引类型: {type(self.index).__name__}")
        print(f"检索方式: 内积（向量已 L2 归一化 = 余弦相似度）")
        if self.full_mode:
            print(f"元数据映射: {len(self.id_to_idx)} 个 chunk_id，"
                  f"{len(self.idx_to_doc)} 段文本")
            print(f"metadata.pkl: {META_FILE.stat().st_size / 1e6:.1f} MB")
        else:
            print("文本映射: 不可用（内存不足降级模式）")

    def by_index(self, idx: int) -> None:
        if not (0 <= idx < self.index.ntotal):
            print(f"行号越界，有效范围 [0, {self.index.ntotal - 1}]")
            return
        vec = np.array(self.index.reconstruct(idx), dtype=np.float32)
        print(f"==== FAISS 第 {idx} 行向量 ====")
        print(" " + vec_summary(vec))
        if self.full_mode:
            cid = self._id_at(idx)
            if cid:
                print(f"chunk_id: {cid}")
            doc = self.idx_to_doc.get(idx, "")
            print(f"文本预览: {doc[:120]!r}" + ("..." if len(doc) > 120 else ""))
            meta = self.idx_to_meta.get(idx, {})
            if meta:
                print("元数据:", {k: meta[k] for k in list(meta)[:6]})

    def _id_at(self, idx: int) -> str:
        for cid, i in self.id_to_idx.items():
            if i == idx:
                return cid
        return ""

    def by_chunk_id(self, cid: str) -> None:
        if not self.full_mode:
            print("降级模式下无 chunk_id 映射，请改用 --index <行号>")
            return
        idx = self.id_to_idx.get(cid)
        if idx is None:
            print(f"未找到 chunk_id: {cid}")
            return
        print(f"chunk_id {cid} → FAISS 第 {idx} 行")
        self.by_index(idx)

    def search_text(self, keyword: str, limit: int = 5) -> None:
        if not self.full_mode:
            print("降级模式下无文本索引，请改用 --index <行号>")
            return
        hits = []
        for idx, text in self.idx_to_doc.items():
            if keyword in text:
                hits.append(idx)
            if len(hits) >= limit:
                break
        if not hits:
            print(f"未找到包含「{keyword}」的 chunk")
            return
        print(f"包含「{keyword}」的 chunk（前 {limit} 个）：")
        for idx in hits:
            self.by_index(idx)
            print("-" * 60)

    def query_demo(self, query: str, top_k: int = 3) -> None:
        """演示检索：查询文本向量化后与库内向量比对（调用 embedding API，有费用）。"""
        import faiss
        from app.rag.embeddings.dashscope_embeddings import get_embeddings

        print(f"查询: {query}")
        emb = get_embeddings().embed_query(query)
        vec = np.array([emb], dtype=np.float32)
        faiss.normalize_L2(vec)
        dists, indices = self.index.search(vec, top_k)
        print(f"查询向量: {vec_summary(np.array(emb, dtype=np.float32))}")
        print()
        for i, (idx, ip) in enumerate(zip(indices[0], dists[0])):
            if idx < 0:
                continue
            score = (float(ip) + 1.0) / 2.0
            print(f"Top{i + 1} | FAISS行 {idx} | 相似度 {score:.4f}")
            if self.full_mode:
                doc = self.idx_to_doc.get(idx, "")
                print(f"  文本: {doc[:100]!r}")
                meta = self.idx_to_meta.get(idx, {})
                print(f"  文档: {meta.get('document_name', '?')[:50]} | "
                      f"章节: {meta.get('chapter', '')[:30]} | "
                      f"来源: {meta.get('source_url', '')[:60]}")
            print()

    def interactive(self) -> None:
        print("向量数据库交互模式（输入 h 查看帮助，q 退出）")
        while True:
            try:
                cmd = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not cmd:
                continue
            if cmd in ("q", "quit", "exit"):
                break
            if cmd in ("h", "help"):
                print("s               总览统计")
                print("i <行号>       查看 FAISS 第 N 行向量")
                print("c <chunk_id>   按 chunk_id 查看（如 doc_427_chunk_0）")
                print("f <关键词>     按 chunk 文本搜索")
                print("q              退出")
                continue
            if cmd == "s":
                self.stats()
            elif cmd.startswith("i "):
                self.by_index(int(cmd[2:]))
            elif cmd.startswith("c "):
                self.by_chunk_id(cmd[2:])
            elif cmd.startswith("f "):
                self.search_text(cmd[2:])
            else:
                print("未知命令，输入 h 查看帮助")


def main() -> None:
    parser = argparse.ArgumentParser(description="向量数据库查看工具")
    parser.add_argument("--stats", action="store_true", help="总览统计")
    parser.add_argument("--index", type=int, default=None, help="按 FAISS 行号查看")
    parser.add_argument("--chunk", default=None, help="按 chunk_id 查看")
    parser.add_argument("--search", default=None, help="按 chunk 文本关键词搜索")
    parser.add_argument("--query", default=None, help="演示检索（调用 embedding API，有费用）")
    args = parser.parse_args()

    insp = VectorInspector()

    if args.query:
        insp.query_demo(args.query)
    elif args.chunk:
        insp.by_chunk_id(args.chunk)
    elif args.index is not None:
        insp.by_index(args.index)
    elif args.search:
        insp.search_text(args.search)
    elif args.stats:
        insp.stats()
    else:
        insp.stats()
        insp.interactive()


if __name__ == "__main__":
    main()
