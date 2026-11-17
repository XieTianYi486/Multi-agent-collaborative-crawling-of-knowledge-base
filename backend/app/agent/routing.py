# ============================================================
# 助手意图门控（轻量模块，不依赖 LLM / FastAPI）
#
# 只有任务、个人数据、找资料类问题才进入工具链路；
# 普通概念问答继续走 RAG，避免多一次模型调用拖慢首字。
# ============================================================

from typing import Tuple

from app.rag.query_processor.intent_recognition import detect_intent

# 刻意保持收敛：普通概念问答（"什么是中断""I2C 时序"）不在此列。
TASK_TOOL_HINTS: Tuple[str, ...] = (
    "提交", "补采", "工单", "人工", "反馈", "通知", "未读", "我的",
    "进度", "到哪了", "状态", "审核", "待办", "待审核", "待处理",
    "班级", "学生", "学情", "任教", "我教",
    "热点", "高频", "未解答", "答不上", "没答上", "周报", "学习画像",
    "学习情况", "活跃度", "积压", "运营", "使用情况", "账号", "登录情况", "审计",
    "帮我找", "有没有", "找一下", "推荐", "资料", "课件", "讲义",
    "习题", "试题", "视频", "文档在哪", "下载",
)


def should_use_tools(question: str, role_code: str = "") -> bool:
    """判断当前提问是否需要进入工具链路"""
    text = (question or "").strip()
    if len(text) < 2:
        return False
    if detect_intent(text) in ("greeting", "rejected"):
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in TASK_TOOL_HINTS)
