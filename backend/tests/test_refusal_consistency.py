# ============================================================
# 拒答文案一致性测试
# 保证 chat_service 拒答文案能被 save_chat_log 的 refusal_patterns
# 命中，否则问答日志的 is_answered 判定会失真（统计页已解答率错误）
# ============================================================

from app.services.chat_service import REFUSAL_FALLBACK_ANSWER
from app.rag.prompts.chat_prompt import SYSTEM_PROMPT_TEMPLATE


REFUSAL_PATTERNS = [
    "未找到相关信息", "未找到关于", "知识库中未找到", "无法回答",
    "建议您咨询", "无法获取", "参考资料中未涉及", "未涉及",
    "未找到与您问题相关的信息",
]


class TestRefusalConsistency:
    def test_fallback_answer_matches_refusal_patterns(self):
        """chat_service 无候选拒答文案必须命中至少一个 refusal_patterns"""
        assert any(p in REFUSAL_FALLBACK_ANSWER for p in REFUSAL_PATTERNS)

    def test_prompt_refusal_instruction_matches_patterns(self):
        """System Prompt 中指导 LLM 的拒答话术也必须命中 refusal_patterns"""
        refusal_text = "抱歉，知识库中未找到与您问题相关的资料。您可尝试换个问法，或等待爬取流水线收录更多内容。"
        assert refusal_text in SYSTEM_PROMPT_TEMPLATE
        assert any(p in refusal_text for p in REFUSAL_PATTERNS)

    def test_prompt_has_disclaimer(self):
        """回答末尾必须附加资料参考声明"""
        assert "以上内容基于知识库收录资料整理" in SYSTEM_PROMPT_TEMPLATE
        assert "仅供教学参考" in SYSTEM_PROMPT_TEMPLATE

    def test_prompt_citation_format(self):
        """Prompt 必须约束来源引用格式 [来源N]"""
        assert "[来源N]" in SYSTEM_PROMPT_TEMPLATE
        assert "原文链接" in SYSTEM_PROMPT_TEMPLATE
