# ============================================================
# 查询改写（Query Rewrite）
# 使用 LLM 对用户问题进行优化，提升检索效果
# ============================================================

import json
from typing import List, Optional

from app.rag.llm.dashscope_llm import get_llm
from app.core.config import settings


QUERY_REWRITE_PROMPT = """你是人工智能学院教学知识库的查询优化助手。你的任务是将师生关于嵌入式开发（ESP32 / ESP-IDF / 树莓派 / 电子电路 / 物联网）学习的口语化问题改写为更适合检索教学资料与官方文档的查询语句。

【改写规则】
1. 将口语化表达规范为专业术语：例如"板子点不亮"→"ESP32 启动失败 调试"；"程序烧不进去"→"ESP32 固件烧录 flash 失败"；"这个传感器怎么接"→"传感器 接线 引脚 电路"。
2. 补全指代与简称：如"IDF"→"ESP-IDF"；"树莓派"→"Raspberry Pi"；"I2C/SPI/UART"等外设缩写补全为"总线 通信 协议"；结合对话历史消解指代（如"那它的引脚呢"应结合上文补全为"型号 引脚定义"）。
3. 提取核心技术概念与同义表述（如"编译/构建"→"编译 构建 工具链"；"WiFi 连不上"→"Wi-Fi 连接 失败 排查"）。
4. 只生成 1 个语义等价但表述不同的查询变体，使用正式专业术语。

【输出格式】
请只输出 JSON 格式，不要包含其他内容：
{{
  "rewritten": "改写后的主要查询",
  "variants": ["变体1"]
}}

【用户问题】
{question}
"""


# 指代/口语化标记：命中时才值得付出一次 LLM 改写
_PRONOUN_MARKERS = ("这", "那", "它", "其", "该", "此", "上面", "刚才", "刚刚", "前面")
_COLLOQUIAL_MARKERS = (
    "点不亮", "连不上", "烧不进", "跑不起", "不工作", "没法", "咋", "为啥", "咋办", "怎么弄",
)


def should_rewrite(question: str, chat_history: Optional[List[dict]] = None) -> bool:
    """按配置判断当前问题是否需要 LLM 改写。

    conditional 模式下，只有短问句、含指代/口语表达或带对话历史时才改写，
    避免对表述完整的技术问题白白增加 1 秒以上延迟。
    """
    mode = (settings.QUERY_REWRITE_MODE or "conditional").lower()
    if mode == "off":
        return False
    if mode == "always":
        return True

    if chat_history:
        return True
    q = (question or "").strip()
    if len(q) < settings.QUERY_REWRITE_MIN_CHARS:
        return True
    return any(m in q for m in _PRONOUN_MARKERS + _COLLOQUIAL_MARKERS)


class QueryRewriter:
    """
    查询改写器（人工智能学院教学领域）

    策略：
    1. 口语转专业术语（如"模型不收敛"→"模型 训练 不收敛 排查"）
    2. 上下文补全（结合多轮对话历史做指代消解）
    3. 生成多个查询变体以提升召回率
    """

    def __init__(self):
        self.llm = get_llm()

    def rewrite(
        self,
        question: str,
        chat_history: Optional[List[dict]] = None,
    ) -> dict:
        """
        改写用户问题

        参数:
            question: 原始问题
            chat_history: 对话历史 [{"role": "user"|"assistant", "content": "..."}]

        返回:
            {
                "rewritten": "改写后的查询",
                "variants": ["变体1", "变体2"],
                "keywords": ["关键词1", ...]
            }
        """
        # 构建带历史的 prompt
        prompt = QUERY_REWRITE_PROMPT.format(question=question)

        if chat_history and len(chat_history) > 0:
            # 注入对话历史，帮助指代消解
            history_text = ""
            for msg in chat_history[-4:]:  # 最近 2 轮对话
                role = "用户" if msg["role"] == "user" else "助手"
                history_text += f"{role}: {msg['content']}\n"
            prompt = prompt.replace(
                "【用户问题】",
                f"【对话历史】\n{history_text}\n\n【用户问题】"
            )

        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=160,
            )

            content = response["content"].strip()
            # 提取 JSON（可能包裹在代码块中）
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]

            result = json.loads(content)
            return {
                "rewritten": result.get("rewritten", question),
                "variants": result.get("variants", [question]),
                "keywords": result.get("keywords", []),
            }

        except Exception:
            # 降级：原样返回
            return {
                "rewritten": question,
                "variants": [question],
                "keywords": [],
            }


# --- 全局单例 ---
_query_rewriter: Optional[QueryRewriter] = None


def get_query_rewriter() -> QueryRewriter:
    """获取查询改写器单例"""
    global _query_rewriter
    if _query_rewriter is None:
        _query_rewriter = QueryRewriter()
    return _query_rewriter
