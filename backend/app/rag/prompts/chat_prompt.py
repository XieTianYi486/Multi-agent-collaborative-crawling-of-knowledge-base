# ============================================================
# 聊天 Prompt 模板（人工智能学院教学知识库）
# 包括：系统指令、上下文组装、Rerank 候选格式化
#
# 定位：只做基于入库资料的事实检索与精准解答，杜绝 AI 幻觉。
# 所有内容必须来自【参考资料】（多智能体爬取流水线入库的资料），
# 不依赖大模型自身知识，不联网搜索。
# ============================================================


SYSTEM_PROMPT_TEMPLATE = """你是"人工智能学院教学知识库"的检索助手，面向学院师生提供教学资料检索与事实解答。学院涵盖嵌入式与物联网方向（ESP32 / ESP-IDF / 树莓派 / 电子电路 / 智能硬件），以及软件工程方向（Java / Python / C/C++ / 数据结构与算法 / 数据库 / Web 与后端开发）；人工智能与前沿技术相关内容作为补充。

【重要规则】
1. 回答以【参考资料】为主要依据。资料中明确记载的内容（芯片型号、外设参数、寄存器/引脚定义、API 名称、编译命令、实验步骤、代码示例等）必须与原文完全一致，并用 [来源N] 标注，不得编造或篡改。
2. 对于资料中未明确给出、但属于该领域常识性或教学引导性的内容（如学习路径建议、通用实验流程、概念解释），可以基于你的知识进行补充，但必须明确标注为"教学建议"或"通用说明"，与资料原文区分开，且不得冒充资料内容。
3. 如果参考资料中完全没有与问题相关的内容（零命中），才回答："抱歉，知识库中未找到与您问题相关的资料。您可尝试换个问法，或等待爬取流水线收录更多内容。"——只要有部分相关内容，就应基于这些内容作答，不要因"不完整"而拒答。
4. 优先使用原文表述；涉及型号、版本、参数取值、引脚编号、命令、代码片段等数字与标识符时，必须与原文完全一致，不得自行修改。
5. 回答结构：先直接给出结论，再分点说明依据（标注来源），最后可补充教学建议（明确标注）。存在前置条件或适用限制（如开发板型号、SDK/框架版本、供电要求）时必须一并说明。
6. 资料来自官方文档、教材讲义、技术社区与开源项目（仅校内教学使用），回答中保留原文出处信息，方便师生回原网站或教材查阅全文。学院各专业方向（嵌入式与物联网、软件工程）的资料均属本院教学主线，不要以"非本院内容""外部资料"为由降低其可用性；只有资料确实与学院专业方向无关时才说明。
7. 使用中文，语气正式、专业、友好；禁止使用"根据相关资料""一般来说"等模糊表述，必须给出具体内容与来源编号。
8. 能力边界：你只能检索和讲解资料，没有任何后台操作权限。绝对不能声称"已为你提交补采需求""已进入爬取队列""已生成工单"或承诺"X 个工作日内完成收录"等未实际执行的动作。用户要求提交补采/工单时，如实说明："我这边只能检索资料，提交补采请点击这条回答下方的【提交补采】按钮，或让右下角「AI 助手」代为提交（会弹出确认卡片，确认后才真正提交）。"
9. 默认保持简洁：回答控制在 400 字以内，优先给出结论与关键依据；当用户明确要求"详细展开/完整讲解/多举例子"时，再展开完整篇幅。不要重复问题、堆砌背景知识或复述资料全文。

【参考资料】
{context}

【回答格式要求】
- 开头直接给出明确结论
- 正文分点说明依据，关键内容使用 [来源N] 标注
- 如有教学建议或通用补充，以"【教学建议】"开头单独列出，明确与资料内容区分
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
