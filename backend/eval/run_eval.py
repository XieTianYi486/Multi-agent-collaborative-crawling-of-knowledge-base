# ============================================================
# 人工智能学院教学知识库 - 评测脚本
#
# 分级运行：
#   L1 无 API Key：  python eval/run_eval.py --retrievers bm25
#   L2 有 API Key：  python eval/run_eval.py --retrievers all
#   L3 端到端评测：  python eval/run_eval.py --mode e2e [--sample-size 40]
#
# 检索指标：HitRate@5 / Recall@5 / Recall@10 / MRR@10 / nDCG@10（binary 相关性）
# 黄金 chunk 判定：document_name 相等 + chapter 子串匹配（可选）
#                 + must_contain 全部子串命中（可选），不依赖 chunk_id
# ============================================================

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

# 将 backend 目录加入 Python 路径（与生产环境一致导入 app.*）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.rag.retrievers.bm25_retriever import get_bm25_retriever
from app.rag.retrievers.hybrid_retriever import get_hybrid_retriever
from app.rag.retrievers.vector_retriever import get_vector_retriever
from app.rag.reranker.llm_reranker import get_reranker
from app.rag.query_processor.query_rewrite import get_query_rewriter

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "qa_dataset.json"
RESULTS_DIR = EVAL_DIR / "results"

# 拒答判定模式（与 chat_service.save_chat_log 的 refusal_patterns 保持一致）
REFUSAL_PATTERNS = [
    "未找到相关信息", "未找到关于", "知识库中未找到", "无法回答",
    "建议您咨询", "无法获取", "参考资料中未涉及", "未涉及",
    "未找到与您问题相关的信息",
]

RETRIEVAL_CONFIGS = ["bm25", "dense", "hybrid", "hybrid_rerank", "hybrid_rerank_rewrite"]


# ---------- 数据集与黄金命中 ----------

def load_dataset() -> list:
    with open(DATASET_PATH, encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]
    for it in items:
        it.setdefault("history", [])
        it.setdefault("gold_chunks", [])
        it.setdefault("security_level", 1)
        it.setdefault("expect_refusal", False)
    return items


def chunk_hits(chunk: dict, gold_chunks: list) -> bool:
    """判断单个检索结果是否命中任一黄金 chunk"""
    doc_name = chunk.get("document_name", "") or ""
    chapter = chunk.get("chapter", "") or ""
    content = chunk.get("content", "") or ""
    for g in gold_chunks:
        if g.get("doc") and doc_name != g["doc"]:
            continue
        if g.get("chapter") and g["chapter"] not in chapter:
            continue
        must = g.get("must_contain") or []
        if must and not all(mc in content for mc in must):
            continue
        return True
    return False


def matched_gold_count(gold_chunks: list, chunks: list) -> int:
    """统计 top-k 结果命中的去重黄金条目数（用于 Recall）"""
    hit = set()
    for gi, gold in enumerate(gold_chunks):
        for c in chunks:
            doc_name = c.get("document_name", "") or ""
            chapter = c.get("chapter", "") or ""
            content = c.get("content", "") or ""
            if gold.get("doc") and doc_name != gold["doc"]:
                continue
            if gold.get("chapter") and gold["chapter"] not in chapter:
                continue
            must = gold.get("must_contain") or []
            if must and not all(mc in content for mc in must):
                continue
            hit.add(gi)
            break
    return len(hit)


# ---------- 检索配置 ----------

def get_visible_doc_ids(security_level: int) -> set:
    """与线上 chat_service._visible_doc_ids 一致的三重过滤"""
    from app.services.chat_service import ChatService
    return ChatService._visible_doc_ids(security_level)


def _merge_by_chunk_id(chunk_lists: list) -> list:
    """多查询结果按 chunk_id 合并（保留最高分），与线上 _multi_query_search 语义一致"""
    merged: dict = {}
    for chunks in chunk_lists:
        for c in chunks:
            cid = c.get("chunk_id", "") or str(c.get("document_id", "")) + c.get("content", "")[:8]
            if cid in merged:
                if c.get("score", 0) > merged[cid].get("score", 0):
                    merged[cid] = c
            else:
                merged[cid] = c
    return sorted(merged.values(), key=lambda c: c.get("score", 0), reverse=True)


def retrieve(config: str, question: str, history: list, security_level: int,
             visible_ids: set, reranker, rewriter, hybrid, bm25, vector) -> list:
    """按配置执行检索，返回 top-10 chunk 列表（与线上过滤一致）"""
    top_k = 10

    if config == "bm25":
        results = [c for c, _ in bm25.search(question, top_k=top_k, security_level=security_level)]
        results = [c for c in results if c.get("document_id") in visible_ids]
        return results[:top_k]

    if config == "dense":
        results = vector.search(question, top_k=top_k, security_level=security_level)
        results = [c for c in results if c.get("document_id") in visible_ids]
        return results[:top_k]

    if config == "hybrid":
        results = hybrid.search(question, top_k=top_k, security_level=security_level)
        results = [c for c in results if c.get("document_id") in visible_ids]
        return results[:top_k]

    if config == "hybrid_rerank":
        candidates = hybrid.search(question, top_k=20, security_level=security_level)
        candidates = [c for c in candidates if c.get("document_id") in visible_ids]
        return reranker.rerank(question, candidates)[:top_k]

    if config == "hybrid_rerank_rewrite":
        rewrite = rewriter.rewrite(question, chat_history=history)
        queries = [rewrite.get("rewritten", question)] + rewrite.get("variants", [])
        queries = [q for q in queries if q]
        candidates = _merge_by_chunk_id(
            [hybrid.search(q, top_k=20, security_level=security_level) for q in queries]
        )
        candidates = [c for c in candidates if c.get("document_id") in visible_ids]
        return reranker.rerank(question, candidates)[:top_k]

    raise ValueError(f"未知检索配置: {config}")


# ---------- 检索质量评测 ----------

def run_retrieval_eval(items: list, configs: list, security_level: int) -> dict:
    """检索评测（bm25 可完全离线；其余配置需要 DASHSCOPE_API_KEY）"""
    bm25 = get_bm25_retriever()
    if bm25.is_empty:
        print("[错误] BM25 索引为空，请先运行 seed_documents.py 完成数据灌入。")
        sys.exit(1)

    visible_ids = get_visible_doc_ids(security_level)
    print(f"  可见文档数（密级<={security_level} 且已发布已过审）: {len(visible_ids)}")

    retr_items = [it for it in items if not it["expect_refusal"]]
    has_key = bool(settings.DASHSCOPE_API_KEY)

    vector = hybrid = reranker = rewriter = None
    need_api = any(c != "bm25" for c in configs)
    if need_api:
        if not has_key:
            print("  [降级] 未配置 DASHSCOPE_API_KEY，仅运行 bm25 配置。")
            configs = ["bm25"]
        else:
            vector = get_vector_retriever()
            hybrid = get_hybrid_retriever()
    if "hybrid_rerank" in configs or "hybrid_rerank_rewrite" in configs:
        reranker = get_reranker()
    if "hybrid_rerank_rewrite" in configs:
        rewriter = get_query_rewriter()

    results = {}
    for config in configs:
        print(f"\n  == 配置: {config} ==")
        per_q = []
        for it in retr_items:
            t0 = time.time()
            try:
                chunks = retrieve(config, it["question"], it.get("history", []),
                                  security_level, visible_ids, reranker, rewriter,
                                  hybrid, bm25, vector)
            except Exception as e:
                print(f"    [失败] {it['id']}: {e}")
                per_q.append({"rel": [], "n_gold": 1, "h5": 0, "h10": 0, "lat": 0})
                continue
            per_q.append({
                "rel": [1 if chunk_hits(c, it["gold_chunks"]) else 0 for c in chunks],
                "n_gold": max(len(it["gold_chunks"]), 1),
                "h5": matched_gold_count(it["gold_chunks"], chunks[:5]),
                "h10": matched_gold_count(it["gold_chunks"], chunks[:10]),
                "lat": (time.time() - t0) * 1000,
            })

        n = len(per_q)
        hit5 = sum(1 for q in per_q if any(q["rel"][:5])) / n
        recall5 = sum(q["h5"] / q["n_gold"] for q in per_q) / n
        recall10 = sum(q["h10"] / q["n_gold"] for q in per_q) / n

        mrr = 0.0
        for q in per_q:
            for i, r in enumerate(q["rel"][:10]):
                if r:
                    mrr += 1.0 / (i + 1)
                    break
        mrr /= n

        ndcg = 0.0
        for q in per_q:
            dcg = sum((1.0 if r else 0.0) / math.log2(i + 2) for i, r in enumerate(q["rel"][:10]))
            ideal = sum(1.0 / math.log2(i + 2) for i in range(min(q["n_gold"], 10)))
            ndcg += dcg / ideal if ideal > 0 else 0.0
        ndcg /= n

        results[config] = {
            "hit_rate@5": round(hit5, 4),
            "recall@5": round(recall5, 4),
            "recall@10": round(recall10, 4),
            "mrr@10": round(mrr, 4),
            "ndcg@10": round(ndcg, 4),
            "avg_latency_ms": round(sum(q["lat"] for q in per_q) / n, 1),
            "num": n,
        }
        r = results[config]
        print(f"    HitRate@5={r['hit_rate@5']:.3f}  Recall@5={r['recall@5']:.3f}  "
              f"Recall@10={r['recall@10']:.3f}  MRR@10={r['mrr@10']:.3f}  "
              f"nDCG@10={r['ndcg@10']:.3f}  平均延迟={r['avg_latency_ms']}ms")
    return results


# ---------- 端到端评测 ----------

CITATION_RE = re.compile(r"《([^》]+)》第?([一二三四五六七八九十百]+)条")


def extract_citations(text: str) -> set:
    """提取答案中的法条引用，如 《劳动合同法》第四十七条"""
    refs = set()
    for m in CITATION_RE.finditer(text):
        refs.add(f"《{m.group(1)}》第{m.group(2)}条")
    return refs


def llm_judge(question: str, standard_answer: str, answer: str) -> int:
    """LLM 判分：2=正确完整 1=部分正确 0=错误或未回答"""
    from app.rag.llm.dashscope_llm import get_llm
    llm = get_llm()
    prompt = (
        "你是劳动法问答评测员。请对照标准答案给系统回答打分。\n"
        "评分标准：2分=结论正确且依据完整；1分=结论正确但依据不完整或存在小瑕疵；0分=结论错误、无关或未回答。\n"
        f"【问题】{question}\n"
        f"【标准答案】{standard_answer}\n"
        f"【系统回答】{answer}\n"
        "只输出一个数字：0、1 或 2。"
    )
    try:
        resp = llm.chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=10)
        m = re.search(r"[012]", resp.get("content", ""))
        return int(m.group()) if m else 1
    except Exception:
        return 1  # 判分失败时按中性处理


def run_e2e(items: list, security_level: int, sample_size: int = 0) -> dict:
    """端到端评测：调用线上 chat_service.ask，含答案判分、引用正确率、拒答统计"""
    from app.services.chat_service import get_chat_service
    service = get_chat_service()

    candidates = [it for it in items if not it["expect_refusal"]]
    refusal_items = [it for it in items if it["expect_refusal"]]
    if sample_size and 0 < sample_size < len(candidates):
        candidates = candidates[:sample_size]

    scores = []
    cite_exact = cite_partial = cite_total = 0
    latencies = []
    correct_refusals = 0
    mis_refusals = 0

    print(f"\n  端到端评测: {len(candidates)} 道正常题 + {len(refusal_items)} 道应拒答题")

    for it in candidates:
        try:
            result = service.ask(question=it["question"], security_level=security_level,
                                 chat_history=it.get("history") or None)
        except Exception as e:
            print(f"    [失败] {it['id']}: {e}")
            continue
        latencies.append(result.get("latency", {}).get("total_ms", 0))
        answer = result.get("answer", "")
        score = llm_judge(it["question"], it["standard_answer"], answer)
        scores.append(score)

        if any(p in answer for p in REFUSAL_PATTERNS):
            mis_refusals += 1
        if it["law_refs"]:
            cite_total += 1
            cited = extract_citations(answer)
            expected = set(it["law_refs"])
            if cited == expected:
                cite_exact += 1
            if cited & expected:
                cite_partial += 1
        print(f"    [{it['id']}] judge={score} 引用={sorted(extract_citations(answer))}")

    for it in refusal_items:
        try:
            result = service.ask(question=it["question"], security_level=security_level)
        except Exception:
            continue
        answer = result.get("answer", "")
        if any(p in answer for p in REFUSAL_PATTERNS) or not result.get("sources"):
            correct_refusals += 1

    n = len(scores)
    e2e = {
        "answer_accuracy_avg": round(sum(scores) / n, 3) if n else 0.0,
        "answer_correct_rate": round(sum(1 for s in scores if s == 2) / n, 3) if n else 0.0,
        "citation_exact": f"{cite_exact}/{cite_total}",
        "citation_partial": f"{cite_partial}/{cite_total}",
        "correct_refusal": f"{correct_refusals}/{len(refusal_items)}",
        "mis_refusal_on_normal": f"{mis_refusals}/{n}",
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
    }
    print("\n  端到端结果:")
    for k, v in e2e.items():
        print(f"    {k}: {v}")
    return e2e


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser(description="人工智能学院教学知识库评测")
    parser.add_argument("--retrievers", default="bm25",
                        help="检索配置：bm25 | all | 逗号分隔（dense,hybrid,hybrid_rerank,hybrid_rerank_rewrite）")
    parser.add_argument("--mode", default="retrieval", choices=["retrieval", "rerank", "e2e"],
                        help="retrieval=检索指标 rerank=检索+重排指标 e2e=端到端（需 LLM）")
    parser.add_argument("--security-level", type=int, default=1,
                        help="评测所用密级（1~4），用于密级过滤实验")
    parser.add_argument("--sample-size", type=int, default=0,
                        help="端到端抽样数量（0=全部），控制 API 配额消耗")
    parser.add_argument("--out", default="", help="结果 JSON 输出路径（默认 results/ 下自动命名）")
    args = parser.parse_args()

    print("=" * 60)
    print("  人工智能学院教学知识库 - 评测")
    print(f"  模式: {args.mode} | 密级: {args.security_level}")
    print(f"  API Key: {'已配置' if settings.DASHSCOPE_API_KEY else '未配置（仅 BM25 可用）'}")
    print("=" * 60)

    items = load_dataset()
    print(f"  评测集: {len(items)} 道题")
    for cat in sorted({it['category'] for it in items}):
        cnt = sum(1 for it in items if it['category'] == cat)
        print(f"    - {cat}: {cnt}")

    if args.mode in ("retrieval", "rerank"):
        if args.retrievers == "all":
            configs = list(RETRIEVAL_CONFIGS)
        else:
            configs = [c.strip() for c in args.retrievers.split(",") if c.strip()]
        results = run_retrieval_eval(items, configs, args.security_level)
        report = {"mode": args.mode, "security_level": args.security_level, "configs": results}
    elif args.mode == "e2e":
        results = run_e2e(items, args.security_level, args.sample_size)
        report = {"mode": "e2e", "security_level": args.security_level, "results": results}
    else:
        report = {}

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else RESULTS_DIR / \
        f"eval_{args.mode}_level{args.security_level}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
