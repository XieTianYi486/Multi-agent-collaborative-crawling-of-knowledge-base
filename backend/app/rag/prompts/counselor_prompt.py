# ============================================================
# AI 导员 Prompt 模板（温柔有耐心的学业生活辅导员）
#
# 与教学知识库问答（chat_prompt.py）完全独立：
# - 不复用"严格技术资料检索"指令
# - 走"人设陪伴 + 导员知识库事务作答"双模式
# - 硬性纪律：涉及具体校规/处分/学术规范等事实，只依据【导员知识库】作答，
#   检索不到就如实说明并引导线下核实，绝不允许编造
# ============================================================


from typing import Optional


COUNSELOR_SYSTEM_PROMPT = """你是"人工智能学院"的学业生活辅导员，同学们都亲切地叫你"导员"。你的性格温柔、耐心、有同理心，是学生遇到困难时第一个愿意倾诉的人。

【你的角色定位】
1. 你是学生的贴心导员，不是冷冰冰的客服。先接住学生的情绪，再回应具体问题。
2. 语气温暖亲切，多用"我懂你""别着急""咱们一起看看"这类有温度的表达。
3. 耐心倾听，不打断、不评判、不说教；学生焦虑或低落时，先安抚情绪再给建议。

【关于你自己（唯一可信的自身信息）】
- 你的办公室只有一个固定说法：**F楼402导员办公室**。同学问"导员办公室在哪""去哪找你"时，只说这一句，不得换用其他叫法。
- 除"F楼402导员办公室"这个名称外，你对办公室本身一无所知：门牌样式、门口摆放的物件、室内陈设装潢、周边房间、同层设施、楼内指示牌或任何找路方式，你全部不掌握。**严禁描述、暗示或以任何方式补充这些细节**（例如"门口有一盆绿萝""看一楼指示牌就能找到""隔壁是某某空间""同层有某某室""到一楼服务台问路"），也不要给出或建议任何找路指引（包括让同学问路、找服务台/前台、看指示牌）。同学问起时，只答"我只知道在F楼402，具体怎么走、周边是什么，我这边确实不清楚"，并引导同学到办公室当面了解。
- 你没有任何私人联系方式，**严禁暗示自己可以通过微信、短信、手机号、QQ 等联系**（例如"微信/短信告诉我""加我好友"）。除本对话窗口与"我的工单"外，你不掌握也提供不了任何其他联络渠道。
- 不要加入描写办公室场景、陈设或身体动作的旁白（例如"（把桌上的保温杯往旁边挪了挪）""（给你倒了杯水）"），这类细节同样是编造。情绪用语言直接表达即可。
- 除上述外，关于你自身的其他信息（值班表、值班时间、联系电话、微信、办公时间、工作分工、上级部门名称等）你一概不掌握，**不得编造**；需要时引导同学通过"我的工单"提交，或联系本班真实辅导员核实。

【回答纪律（极其重要，必须严格遵守）】
4. 凡涉及"学校相关的具体事实"，你只能转述下方【导员知识库】中明确写到的内容。这类事实包括但不限于：校规校纪、纪律处分、学术不端、学籍、考试、奖助学金、办事流程，以及**开放时间、地点、联系电话、网址、公众号/小程序名称、部门名称、金额、期限**等任何具体信息。
5. 严禁编造。具体而言，你绝对不可以：
   - 编造知识库里没有的条款号、法规名称、处分档次、金额、期限或流程；
   - 引用知识库中未出现的文件名称或条款编号（例如凭空写"依据《××规定》第×条"）；
   - 用你的通用知识、常识或网络记忆去补全学校的具体信息；
   - 编造关于你自身的值班安排、办公时间、联系方式或部门归属（例如凭空说自己在"学生工作部值班"），你的自身信息只以【关于你自己】一节为准；
   - 自行推荐或描述知识库中没有写明的渠道（官网栏目、公众号、小程序、APP、办公地点或房间、办理窗口等）。这类信息只能转述知识库原文写到的内容，否则统一引导同学走"我的工单"或联系本班真实辅导员，绝不自行补充。
6. 【导员知识库】中没有相关内容或信息不足时，请温柔而诚实地说明"这一点我这边没有查到确切依据"，并：
   - 绝不猜测、绝不给近似答案，也不要写"大概是……"；
   - 建议同学通过"我的工单"提交问题，或直接联系本班真实辅导员当面核实。
7. 不承诺任何越权事项（如改成绩、通融考勤、撤销处分、提前解除处分等），一律温和地引导同学走正规流程。
8. 若察觉明显的心理危机、自伤或自杀倾向，先共情安抚，再温和而坚定地引导同学尽快联系学校心理健康中心或本班真实辅导员，并鼓励其向身边可信赖的人求助；你**不做心理诊断**，也不轻视任何求助信号。
9. 不提供任何违纪、作弊、伪造材料等违规行为的操作方法或规避调查的建议。
10. 【历史记忆】是你与这位同学在**既往会话**中的对话要点，只用于延续关心、避免重复追问，**不能当作学校事实的依据**；与【导员知识库】冲突时一律以知识库为准。不要主动复述其中的隐私细节（心理、家庭、情感类尤甚），除非同学本次对话先提起。

【回答风格】
- 口语化、自然、有温度；可以适度分点，但不要写成公文。
- 长度适中、不啰嗦；先给结论，再给依据和下一步建议。
- 仅在【导员知识库】确有对应条款时，才标注来源出处（如《学生纪律处分规定》第十八条），方便同学回原文核对；不得标注未出现在知识库中的来源。
- 若【当前学生】给出了姓名，可以自然地称呼（如"××同学"），但不必每轮都重复，也不要过度亲昵；未给出时，绝不猜测或编造学生的姓名与院系。

【当前学生】
{student}

【导员知识库】
{context}

【历史记忆】
{memory}
"""

# 未获取到登录身份时注入的占位说明：明确禁止猜测学生身份
STUDENT_UNKNOWN = (
    "（本次未获取到该学生的身份信息）\n"
    "【重要提醒】不要询问、猜测或编造学生的姓名、院系、班级等个人信息，"
    "按“同学”泛称即可。"
)

# 未检索到相关内容时注入的占位说明（同时约束模型进入"纯陪伴"行为）
KNOWLEDGE_CONTEXT_EMPTY = (
    "（本次未在导员知识库中检索到与该同学问题直接相关的条款）\n\n"
    "【重要提醒】由于上面没有任何可用条款，本轮你处于「陪伴模式」：\n"
    "你只能倾听、共情并引导同学线下核实，不得回答任何学校相关的具体事实"
    "（包括但不限于开放时间、地点、电话、网址、公众号、部门、金额、期限、流程、"
    "处分档次、法规名称与条款号）。宁可诚实说「我不确定」，也绝不编造。"
)


def _render_cited_context(context_chunks: list) -> str:
    """检索模式：把 top-k 条款按【来源 N】罗列"""
    parts = []
    for i, c in enumerate(context_chunks):
        title = c.get("source_title") or c.get("document_name", "导员知识库")
        article = c.get("article_no", "")
        chapter = c.get("chapter", "")
        source_url = c.get("source_url", "")
        content = c.get("content", "")

        header = f"【来源 {i + 1}】《{title}》"
        if article:
            header += f" {article}"
        if chapter:
            header += f"（{chapter}）"
        if source_url:
            header += f"\n原文链接：{source_url}"
        parts.append(f"{header}\n{content}")

    return "\n\n---\n\n".join(parts)


def render_full_context(context_chunks: list) -> str:
    """
    全量注入模式：把知识库全部条款按"文档 → 章 → 条"分组罗列。

    输出必须稳定（同一份知识库每次渲染结果完全一致），
    这样才能作为固定前缀命中 LLM 侧的 prompt 缓存。
    """
    grouped = {}
    for c in context_chunks:
        key = (c.get("source_title") or "", c.get("source_url") or "")
        grouped.setdefault(key, []).append(c)

    blocks = []
    for (title, source_url), items in grouped.items():
        lines = [f"《{title}》"]
        if source_url:
            lines.append(f"原文链接：{source_url}")
        chapter = None
        for c in items:
            ch = c.get("chapter") or ""
            if ch and ch != chapter:
                chapter = ch
                lines.append(ch)
            article = c.get("article_no") or ""
            content = c.get("content", "")
            lines.append(f"{article}\n{content}" if article else content)
        blocks.append("\n".join(lines))

    return "\n\n===\n\n".join(blocks)


def build_student_block(user_profile: Optional[dict]) -> str:
    """
    把登录用户的身份信息渲染成 system prompt 里的【当前学生】片段。

    user_profile: {"name": "张小明", "department": "动画学院2023级1班"}
    信息由后端从登录态（users 表）取出，属可信事实，不需要模型再去求证。
    """
    if not user_profile:
        return STUDENT_UNKNOWN

    name = (user_profile.get("name") or "").strip()
    department = (user_profile.get("department") or "").strip()

    parts = []
    if name:
        parts.append(f"姓名：{name}")
    if department:
        parts.append(f"院系/班级：{department}")
    if not parts:
        return STUDENT_UNKNOWN

    return "；".join(parts) + "。（以上信息由登录身份提供，可直接采信，无需向同学求证）"


# 没有跨会话历史可参考时的占位说明
MEMORY_EMPTY = "（本次没有可参考的既往会话内容，不要假装记得以前聊过什么）"


def _clip(text: str, limit: int) -> str:
    """压缩空白并把过长文本截断，避免历史记忆挤占 prompt 预算"""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def build_memory_block(turns: Optional[list]) -> str:
    """
    渲染跨会话记忆片段（【历史记忆】）。

    turns: [{"question": "...", "answer": "...", "date": "08-12"}, ...]
           由后端按 user_id 从既往会话中取出、配对并截断，这里只负责排版。
    """
    if not turns:
        return MEMORY_EMPTY

    lines = []
    for turn in turns:
        question = _clip(turn.get("question"), 60)
        answer = _clip(turn.get("answer"), 80)
        date = (turn.get("date") or "").strip()
        prefix = f"[{date}] " if date else ""
        if answer:
            lines.append(f"- {prefix}同学曾问：「{question}」；你当时的回答要点：「{answer}」")
        else:
            lines.append(f"- {prefix}同学曾问：「{question}」（当时未给出回答）")
    return "\n".join(lines)


def build_counselor_system_prompt(
    context_chunks: list,
    full: bool = False,
    user_profile: Optional[dict] = None,
    memory: Optional[list] = None,
) -> str:
    """
    组装导员的 System Prompt

    参数:
        context_chunks: 知识库条款列表，每个包含
                        content, source_title, article_no, chapter, source_url
        full: True=全量注入（条款即完整知识库）；False=检索模式（条款为 top-k 结果）
        user_profile: 登录用户身份 {"name": ..., "department": ...}，用于称呼学生
        memory: 跨会话历史要点，用于让导员记得既往聊过的话题
    """
    student_block = build_student_block(user_profile)
    memory_block = build_memory_block(memory)

    if not context_chunks:
        return COUNSELOR_SYSTEM_PROMPT.format(
            context=KNOWLEDGE_CONTEXT_EMPTY, student=student_block, memory=memory_block,
        )

    context_text = render_full_context(context_chunks) if full else _render_cited_context(context_chunks)
    return COUNSELOR_SYSTEM_PROMPT.format(
        context=context_text, student=student_block, memory=memory_block,
    )


def build_counselor_messages(
    question: str,
    context_chunks: list,
    chat_history: list = None,
    full: bool = False,
    user_profile: Optional[dict] = None,
    memory: Optional[list] = None,
) -> list:
    """
    构建导员对话消息列表（system + 历史 + 当前问题）

    full=True 时条款为完整知识库全量注入，模型自行判断是否涵盖问题。
    user_profile 为登录用户身份，memory 为跨会话历史要点。
    """
    messages = [
        {"role": "system", "content": build_counselor_system_prompt(
            context_chunks, full=full, user_profile=user_profile, memory=memory,
        )}
    ]
    if chat_history:
        messages.extend(chat_history[-10:])  # 最近 10 条（5 轮）
    messages.append({"role": "user", "content": question})
    return messages


# ==================== 问候语 ====================

GREETING_WORDS = ["你好", "您好", "hi", "hello", "早上好", "下午好", "晚上好", "在吗", "嗨"]


def is_counselor_greeting(question: str) -> bool:
    """判断是否为简单问候（走快速人设回应，不做检索）"""
    q = question.strip().lower()
    if len(q) > 15:
        return False
    return any(w.lower() in q for w in GREETING_WORDS)


def get_counselor_greeting() -> str:
    """导员问候语（温柔人设）"""
    return (
        "你好呀，我是你的导员～ 不管是学习上的困惑、生活里的小烦恼，"
        "还是想了解学校的某些规定，都可以随时跟我说。我在这儿陪着你，慢慢来，不着急。"
    )
