# ============================================================
# 查询改写（Query Rewrite）
# 使用 LLM 对用户问题进行优化，提升检索效果
# ============================================================

import json
from typing import List, Optional

from app.rag.llm.dashscope_llm import get_llm
from app.core.config import settings


QUERY_REWRITE_PROMPT = """你是嵌入式开发教学知识库的查询优化助手。你的任务是将师生关于硬件开发的口语化问题改写为更适合检索技术文档的查询语句。

【改写规则】
1. 将口语化表达规范为技术术语：例如"esp32怎么联网"→"ESP32 Wi-Fi 配网 连接教程"；"板子点不亮"→"ESP32 启动失败 电源 调试"；"树莓派装系统"→"树莓派 系统安装 烧录镜像"。
2. 补全指代与简称：如"IDF"→"ESP-IDF 开发框架"；结合对话历史消解指代（如"那它的引脚呢"应结合上文补全为"ESP32 开发板 引脚定义"）。
3. 提取核心技术概念与同义表述（如"烧录/下载/刷机"→"固件烧录"；"传感器"→"传感器 接口 驱动"）。
4. 生成 2-3 个语义等价但表述不同的查询变体，至少一个使用正式技术术语。

【输出格式】
请只输出 JSON 格式，不要包含其他内容：
{{
  "rewritten": "改写后的主要查询",
  "variants": ["变体1", "变体2"],
  "keywords": ["关键词1", "关键词2", "关键词3"]
}}

【用户问题】
{question}
"""


class QueryRewriter:
    """
    查询改写器（嵌入式开发教学领域）

    策略：
    1. 口语转技术术语（如"板子连不上网"→"Wi-Fi 配网"）
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
                max_tokens=256,
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
