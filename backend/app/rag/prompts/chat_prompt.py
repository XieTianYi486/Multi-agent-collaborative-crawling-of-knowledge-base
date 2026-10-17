# ============================================================
# 聊天 Prompt 模板（人工智能学院教学知识库）
# 包括：系统指令、上下文组装、Rerank 候选格式化
#
# 定位：只做基于入库资料的事实检索与精准解答，杜绝 AI 幻觉。
# 所有内容必须来自【参考资料】（多智能体爬取流水线入库的资料），
# 不依赖大模型自身知识，不联网搜索。
# ============================================================


SYSTEM_PROMPT_TEMPLATE = """你是"人工智能学院教学知识库"的检索助手，面向学院师生提供 ESP32、树莓派、嵌入式开发、智能玩具等硬件开发领域的教学资料检索与事实解答。你的所有回答必须严格依据【参考资料】中的内容。

【重要规则】
1. 只能基于【参考资料】的内容回答，不得编造技术参数、接口名称、版本号、日期或结论；参考资料未包含的信息一律不得自行补充，也不得使用你自己的通用知识。
2. 回答中涉及具体技术内容（配置步骤、函数/API 名称、参数值、引脚定义等）时，必须用引用格式 [来源N] 标注（N 对应【参考资料】中的编号）。
3. 如果参考资料中没有相关信息或信息不足，请明确回答："抱歉，知识库中未找到与您问题相关的资料。您可尝试换个问法，或等待爬取流水线收录更多内容。"
4. 优先使用原文表述；涉及引脚号、波特率、命令、版本等数字与标识符时，必须与原文完全一致，不得自行修改。
5. 回答要求：先直接给出明确结论，再分点说明依据；存在前置条件或适用限制（如芯片型号限定、框架版本要求）时必须一并说明。
6. 资料来自官方文档、技术社区与开源项目（仅校内教学使用），回答中保留原文出处信息，方便师生回原网站查阅全文。
7. 使用中文，语气正式、专业、友好；禁止使用"根据相关资料""一般来说"等模糊表述，必须给出具体内容与来源编号。

【参考资料】
{context}

【回答格式要求】
- 开头直接给出明确结论
- 正文分点说明依据，关键内容使用 [来源N] 标注
- 末尾以列表列出本次回答引用的全部来源（含文档名与原文链接）
- 最后一行固定附加声明："以上内容基于知识库收录资料整理，仅供教学参考；完整内容请以来源文档为准。"
"""


def build_system_prompt(context_chunks: list) -> str:
    """
    根据检索到的上下文构建教学知识库问答 System Prompt

    参数:
        context_chunks: 检索到的文档片段列表，每个包含 content, document_name,
                        chapter, page, source_url（可选）

    返回:
        格式化后的 System Prompt 字符串
    """
    if not context_chunks:
        return SYSTEM_PROMPT_TEMPLATE.format(
            context="（知识库中暂无相关内容）"
        )

    # 组装上下文（按相关性排序）
    context_parts = []
    for i, chunk in enumerate(context_chunks):
        doc_name = chunk.get("document_name", "未知文档")
        chapter = chunk.get("chapter", "")
        page = chunk.get("page", "")
        source_url = chunk.get("source_url", "")
        content = chunk.get("content", "")

        source_info = f"【来源 {i + 1}】{doc_name}"
        if chapter:
            source_info += f" - {chapter}"
        if page:
            source_info += f" - 第{page}页"
        if source_url:
            source_info += f"\n原文链接：{source_url}"

        context_parts.append(f"{source_info}\n{content}")

    context_text = "\n\n---\n\n".join(context_parts)

    return SYSTEM_PROMPT_TEMPLATE.format(context=context_text)


def build_chat_messages(
    question: str,
    context_chunks: list,
    chat_history: list = None,
) -> list:
    """
    构建完整的聊天消息列表（system + history + user）

    参数:
        question: 用户当前问题
        context_chunks: 检索到的文档片段
        chat_history: 历史消息列表 [{"role": "user"|"assistant", "content": "..."}]

    返回:
        [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]
    """
    messages = []

    # System Prompt
    system_content = build_system_prompt(context_chunks)
    messages.append({"role": "system", "content": system_content})

    # 历史对话（最近 N 轮）
    if chat_history:
        # 确保不超过上下文窗口
        recent_history = chat_history[-10:]  # 最近 10 条消息（5 轮对话）
        messages.extend(recent_history)

    # 当前问题
    messages.append({"role": "user", "content": question})

    return messages
