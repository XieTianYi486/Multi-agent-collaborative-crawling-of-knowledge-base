# ============================================================
# 评测数据集 schema 校验测试
# 保证 qa_dataset.json 结构正确，避免评测脚本运行时才发现问题
# ============================================================

import json
import re
import sys
from pathlib import Path

# eval 目录在 backend/eval 下，测试运行目录为 backend/
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
DATASET_PATH = EVAL_DIR / "qa_dataset.json"

VALID_CATEGORIES = {
    "工时休假", "工资社保", "劳动合同", "解雇保护", "工伤",
    "争议处理", "企业制度", "案例咨询", "拒答无关", "多轮指代",
}

# 法规引用（含条号）或制度/案例引用（仅文档名，如《考勤与加班管理制度》）
LAW_REF_RE = re.compile(r"^《.+》(第[一二三四五六七八九十百]+条)?$")


def load_items():
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)["items"]


class TestEvalDataset:
    def test_file_exists(self):
        assert DATASET_PATH.exists(), "qa_dataset.json 不存在"

    def test_id_unique(self):
        ids = [it["id"] for it in load_items()]
        assert len(ids) == len(set(ids)), "题目 ID 重复"

    def test_required_fields(self):
        for it in load_items():
            for field in ("id", "category", "question", "standard_answer",
                          "law_refs", "gold_docs", "gold_chunks",
                          "security_level", "expect_refusal"):
                assert field in it, f"{it.get('id')} 缺少字段 {field}"

    def test_category_valid(self):
        for it in load_items():
            assert it["category"] in VALID_CATEGORIES, \
                f"{it['id']} 分类非法: {it['category']}"

    def test_security_level_range(self):
        for it in load_items():
            assert it["security_level"] in (1, 2, 3, 4), \
                f"{it['id']} 密级非法: {it['security_level']}"

    def test_expect_refusal_is_bool(self):
        for it in load_items():
            assert isinstance(it["expect_refusal"], bool)

    def test_law_refs_format(self):
        """引用格式：《法规名》第X条（中文数字）或仅《文档名》（制度/案例）"""
        for it in load_items():
            for ref in it["law_refs"]:
                assert LAW_REF_RE.match(ref), f"{it['id']} 引用格式非法: {ref}"

    def test_refusal_items_have_no_gold(self):
        for it in load_items():
            if it["expect_refusal"]:
                assert not it["gold_chunks"], f"{it['id']} 拒答题不应有黄金 chunk"
                assert not it["law_refs"], f"{it['id']} 拒答题不应有法条引用"

    def test_normal_items_have_gold(self):
        for it in load_items():
            if not it["expect_refusal"]:
                assert it["gold_chunks"], f"{it['id']} 非拒答题缺少黄金 chunk"

    def test_category_distribution(self):
        """各分类题量符合设计：分布不应失衡"""
        counts = {}
        for it in load_items():
            counts[it["category"]] = counts.get(it["category"], 0) + 1
        assert sum(counts.values()) >= 70, "评测集题量不足"
        assert counts.get("拒答无关", 0) >= 4, "拒答样本不足"
        assert counts.get("多轮指代", 0) >= 4, "多轮指代样本不足"

    def test_multi_turn_items_have_history(self):
        for it in load_items():
            if it["category"] == "多轮指代":
                assert len(it.get("history", [])) >= 2, \
                    f"{it['id']} 多轮题缺少对话历史"
