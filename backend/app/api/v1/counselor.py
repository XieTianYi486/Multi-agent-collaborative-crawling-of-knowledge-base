# ============================================================
# AI 导员 交互接口
# POST /api/v1/counselor/ask      - 同步提问
# POST /api/v1/counselor/stream   - 流式提问 (SSE)
# 会话管理 CRUD + 反馈
#
# 与教学问答（/chat）完全独立：会话、日志均走 counselor_* 表，
# 敏感词拦截/脱敏与审计留痕复用既有能力（module 标记为 counselor 区分）
# ============================================================

import json
import logging
import traceback as tb_module
import uuid as uuid_lib
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.db.sqlite import get_db, SessionLocal
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.counselor import CounselorSession, CounselorMessage, CounselorLog
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.counselor import (
    CounselorAskRequest, CounselorSessionCreate,
    CounselorSessionUpdate, CounselorFeedbackRequest,
)
from app.services.counselor_service import CounselorService, get_counselor_service
from app.services.sensitive_service import SensitiveService
from app.services.audit_service import add_audit_log

router = APIRouter(prefix="/counselor", tags=["AI导员"])
logger = logging.getLogger(__name__)


BLOCKED_QUESTION_RESPONSE = (
    "同学你好，你的问题里似乎包含了一些不太合适的内容，我这边没办法回应哦～"
    "如果你遇到了困难，欢迎换个说法告诉我，或者直接联系本班辅导员聊聊。"
)


def _check_question_sensitive(db: Session, question: str, user: User) -> bool:
    """问题侧敏感词拦截：命中则写审计留痕并返回 True"""
    words = SensitiveService.get_enabled_words(db)
    if not SensitiveService.contains_block_word(question, words):
        return False
    add_audit_log(
        db=db, module="counselor", action="sensitive_block", status="blocked",
        user_id=user.id, username=user.username,
        target_type="counselor_chat", detail={"question": question[:200]},
    )
    return True


def _error_stream(message: str) -> StreamingResponse:
    """以 SSE 协议返回错误事件（避免抛出裸 HTTP 500，让前端能给出可读提示）"""
    def gen():
        yield f"event: error\ndata: {json.dumps({'message': message}, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


# ==================== 同步提问 ====================

@router.post("/ask", response_model=APIResponse, summary="导员同步提问")
def ask_counselor(
    request: CounselorAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """同步问答：提交问题后等待完整答案返回"""
    counselor = get_counselor_service()

    user_id: int = current_user.id
    username: str = current_user.username
    role_code: str = current_user.role.code if current_user.role else ""
    security_level = _get_security_level(role_code)

    if _check_question_sensitive(db, request.question, current_user):
        return APIResponse(
            code=0, message="success",
            data={
                "answer": BLOCKED_QUESTION_RESPONSE,
                "sources": [], "mode": "blocked", "session_id": request.session_id,
            },
        )

    chat_history = _load_history(db, request.session_id)

    result = counselor.ask(
        question=request.question, chat_history=chat_history,
        security_level=security_level,
        user_profile=_build_user_profile(current_user),
        memory=_load_cross_session_memory(db, user_id, request.session_id),
    )

    # 回答脱敏
    masked_answer, _ = SensitiveService.mask_answer(
        result["answer"], db, user_id=user_id, username=username,
    )
    result["answer"] = masked_answer

    session_id = request.session_id or _generate_session_id()
    if not request.session_id:
        db.add(CounselorSession(
            id=session_id, user_id=user_id, title=request.question[:50],
        ))

    db.add(CounselorMessage(session_id=session_id, role="user", content=request.question))
    db.add(CounselorMessage(
        session_id=session_id, role="assistant", content=result["answer"],
        mode=result.get("mode"), sources=json.dumps(result.get("sources", [])),
    ))
    db.commit()

    counselor.save_log(
        question=request.question, answer=result["answer"],
        session_id=session_id, user_id=user_id, mode=result.get("mode", ""),
        sources=result.get("sources", []), latency=result.get("latency", {}),
    )

    return APIResponse(code=0, message="success", data={
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "mode": result.get("mode"),
        "session_id": session_id,
    })


# ==================== 流式提问 ====================

@router.post("/stream", summary="导员流式提问 (SSE)")
async def ask_counselor_stream(
    request: CounselorAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    流式问答接口 (Server-Sent Events)

    事件类型:
    - event: token   → {"token": "文字片段"}
    - event: sources → [{"source_title": "...", "article_no": "..."}]
    - event: done    → {"full_answer": "...", "mode": "persona|knowledge"}
    - event: error   → {"message": "错误信息"}
    """
    counselor = get_counselor_service()

    user_id: int = current_user.id
    username: str = current_user.username
    question: str = request.question
    role_code: str = current_user.role.code if current_user.role else ""
    security_level = _get_security_level(role_code)

    # 前置阶段（敏感词校验 / 会话与用户消息落库）一旦失败就以 SSE error 事件返回，
    # 避免向客户端抛出无信息的 HTTP 500
    try:
        blocked = _check_question_sensitive(db, question, current_user)
        session_id = request.session_id or _generate_session_id()

        if not blocked:
            chat_history = _load_history(db, request.session_id)
            # 跨会话记忆需在 db.close() 之前取，之后 db 会话已关闭
            memory = _load_cross_session_memory(db, user_id, request.session_id)

            # 创建/获取会话 + 保存用户消息
            if not request.session_id:
                db.add(CounselorSession(
                    id=session_id, user_id=user_id, title=question[:50],
                ))
                db.flush()
            db.add(CounselorMessage(session_id=session_id, role="user", content=question))
            db.commit()
            db.close()
    except Exception as e:
        logger.exception("导员流式问答前置阶段失败")
        return _error_stream(f"导员服务暂时不可用，请稍后重试（{type(e).__name__}）")

    # 敏感词拦截（以 SSE 协议返回）
    if blocked:
        def blocked_stream():
            yield f"event: token\ndata: {json.dumps({'token': BLOCKED_QUESTION_RESPONSE}, ensure_ascii=False)}\n\n"
            yield f"event: sources\ndata: {json.dumps([], ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'full_answer': BLOCKED_QUESTION_RESPONSE, 'mode': 'blocked', 'sources': []}, ensure_ascii=False)}\n\n"
        return StreamingResponse(blocked_stream(), media_type="text/event-stream")

    stream_result = {"full_answer": "", "sources": [], "mode": "", "ok": False, "latency": {}}

    user_profile = _build_user_profile(current_user)

    async def event_stream():
        try:
            async for event in counselor.ask_stream(
                question=question, chat_history=chat_history,
                security_level=security_level,
                user_profile=user_profile, memory=memory,
            ):
                if event["type"] == "token":
                    stream_result["full_answer"] += event["data"]
                    yield f"event: token\ndata: {json.dumps({'token': event['data']}, ensure_ascii=False)}\n\n"

                elif event["type"] == "sources":
                    stream_result["sources"] = event["data"]
                    yield f"event: sources\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

                elif event["type"] == "done":
                    data = event["data"]
                    stream_result["mode"] = data.get("mode", "")
                    stream_result["latency"] = data.get("latency", {})

                    # 回答脱敏（完成后整体过滤一次）
                    masked = stream_result["full_answer"]
                    hits = []
                    if masked:
                        sdb = SessionLocal()
                        try:
                            masked, hits = SensitiveService.mask_answer(
                                masked, sdb, user_id=user_id, username=username,
                            )
                            sdb.commit()
                        finally:
                            sdb.close()
                        stream_result["full_answer"] = masked
                        if hits:
                            yield f"event: sensitive\ndata: {json.dumps({'full_answer': masked, 'hits': hits}, ensure_ascii=False)}\n\n"

                    data["full_answer"] = masked
                    data["session_id"] = session_id
                    stream_result["ok"] = True
                    yield f"event: done\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                elif event["type"] == "error":
                    yield f"event: error\ndata: {json.dumps({'message': event['data']}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error("导员流式问答异常:\n%s", tb_module.format_exc())
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    def save_assistant_message():
        """后台任务：流式完成后保存助手消息 + 导员日志"""
        if not stream_result["ok"]:
            return
        save_db = SessionLocal()
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)

            save_db.add(CounselorMessage(
                session_id=session_id, role="assistant",
                content=stream_result["full_answer"],
                mode=stream_result["mode"],
                sources=json.dumps(stream_result["sources"]),
                token_count=len(stream_result["full_answer"]) // 3,
            ))
            sess = save_db.query(CounselorSession).filter(
                CounselorSession.id == session_id
            ).first()
            if sess:
                sess.message_count = sess.message_count + 2
                sess.last_message_at = now

            latency = stream_result.get("latency", {})
            save_db.add(CounselorLog(
                session_id=session_id, user_id=user_id, question=question,
                answer=stream_result["full_answer"], mode=stream_result["mode"],
                source_titles=[s.get("source_title", "") for s in stream_result.get("sources", [])],
                is_answered=1 if stream_result["mode"] == "knowledge" else 0,
                retrieval_ms=latency.get("retrieval_ms", 0),
                llm_ms=latency.get("llm_ms", 0),
                total_ms=latency.get("total_ms", 0),
            ))
            save_db.commit()
        except Exception:
            save_db.rollback()
            logger.warning("保存导员助手消息失败:\n%s", tb_module.format_exc())
        finally:
            save_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        background=BackgroundTask(save_assistant_message),
    )


# ==================== 会话管理 ====================

@router.get("/sessions", response_model=APIResponse, summary="导员会话列表")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    sessions = (
        db.query(CounselorSession)
        .filter(CounselorSession.user_id == current_user.id)
        .order_by(CounselorSession.last_message_at.desc().nullslast())
        .all()
    )
    return APIResponse(code=0, message="success", data=[
        {
            "id": s.id, "title": s.title, "message_count": s.message_count,
            "last_message_at": _iso(s.last_message_at), "created_at": _iso(s.created_at),
        }
        for s in sessions
    ])


@router.post("/sessions", response_model=APIResponse, summary="创建导员会话")
def create_session(
    request: CounselorSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = CounselorSession(
        id=_generate_session_id(), user_id=current_user.id,
        title=request.title or "与导员的新对话",
    )
    db.add(session)
    db.flush()
    return APIResponse(code=0, message="会话创建成功",
                       data={"session_id": session.id, "title": session.title})


@router.patch("/sessions/{session_id}", response_model=APIResponse, summary="更新导员会话")
def update_session(
    session_id: str, request: CounselorSessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = db.query(CounselorSession).filter(
        CounselorSession.id == session_id,
        CounselorSession.user_id == current_user.id,
    ).first()
    if not session:
        return APIResponse(code=3001, message="会话不存在")
    if request.title is not None:
        session.title = request.title
        db.flush()
    return APIResponse(code=0, message="更新成功")


@router.delete("/sessions/{session_id}", response_model=APIResponse, summary="删除导员会话")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = db.query(CounselorSession).filter(
        CounselorSession.id == session_id,
        CounselorSession.user_id == current_user.id,
    ).first()
    if not session:
        return APIResponse(code=3001, message="会话不存在")
    db.delete(session)
    db.flush()
    return APIResponse(code=0, message="会话已删除")


@router.get("/sessions/{session_id}/messages", response_model=APIResponse, summary="导员会话消息")
def get_session_messages(
    session_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = db.query(CounselorSession).filter(
        CounselorSession.id == session_id,
        CounselorSession.user_id == current_user.id,
    ).first()
    if not session:
        return APIResponse(code=3001, message="会话不存在")

    query = db.query(CounselorMessage).filter(
        CounselorMessage.session_id == session_id
    ).order_by(CounselorMessage.created_at.asc())
    total = query.count()
    messages = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for m in messages:
        sources = None
        if m.sources:
            try:
                sources = json.loads(m.sources) if isinstance(m.sources, str) else m.sources
            except Exception:
                sources = None
        items.append({
            "id": m.id, "session_id": m.session_id, "role": m.role,
            "content": m.content, "mode": m.mode, "sources": sources,
            "token_count": m.token_count, "created_at": _iso(m.created_at),
        })

    return APIResponse(code=0, message="success",
                       data=PaginatedData.from_query(items, total, page, page_size).model_dump())


# ==================== 反馈 ====================

@router.post("/feedback", response_model=APIResponse, summary="提交导员回答反馈")
def submit_feedback(
    request: CounselorFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    log = db.query(CounselorLog).filter(
        CounselorLog.user_id == current_user.id,
        CounselorLog.session_id == request.session_id,
    ).order_by(CounselorLog.created_at.desc()).first()
    if log:
        log.feedback = request.feedback
        log.feedback_reason = request.reason
        db.flush()
    return APIResponse(code=0, message="感谢你的反馈")


# ==================== Edge TTS 语音合成 ====================

# Edge TTS 可用的中文音色（精选，避免每次都请求列表）
EDGE_TTS_VOICES = [
    {"short_name": "zh-CN-XiaoxiaoNeural", "name": "晓晓", "gender": "Female", "desc": "温柔女声，最常用"},
    {"short_name": "zh-CN-XiaoyiNeural", "name": "晓伊", "gender": "Female", "desc": "活泼女孩声"},
    {"short_name": "zh-CN-YunxiNeural", "name": "云希", "gender": "Male", "desc": "阳光男声"},
    {"short_name": "zh-CN-YunyangNeural", "name": "云扬", "gender": "Male", "desc": "新闻播音男声"},
    {"short_name": "zh-CN-YunjianNeural", "name": "云健", "gender": "Male", "desc": "成熟男声"},
    {"short_name": "zh-CN-XiaomengNeural", "name": "晓梦", "gender": "Female", "desc": "温柔女声"},
    {"short_name": "zh-CN-XiaohanNeural", "name": "晓涵", "gender": "Female", "desc": "知性女声"},
    {"short_name": "zh-CN-YunyeNeural", "name": "云野", "gender": "Male", "desc": "沉稳男声"},
    {"short_name": "zh-CN-XiaoshuangNeural", "name": "晓双", "gender": "Female", "desc": "甜美女声"},
    {"short_name": "zh-CN-XiaoyouNeural", "name": "晓悠", "gender": "Female", "desc": "童声女孩"},
    {"short_name": "zh-CN-XiaozhenNeural", "name": "晓真", "gender": "Female", "desc": "干练女声"},
    {"short_name": "zh-CN-YunxiaNeural", "name": "云夏", "gender": "Male", "desc": "青年男声"},
]


@router.get("/tts/voices", summary="获取 Edge TTS 可用音色列表")
async def list_tts_voices():
    """返回精选的中文 Edge TTS 音色列表"""
    return APIResponse(code=0, message="success", data=EDGE_TTS_VOICES)


@router.get("/tts", summary="Edge TTS 语音合成（返回 mp3 音频流）")
async def tts_synthesize(
    text: str = Query(..., description="要合成的文本"),
    voice: str = Query("zh-CN-XiaoxiaoNeural", description="音色 ShortName"),
    current_user: User = Depends(get_current_active_user),
):
    """
    使用 Edge TTS（微软 Edge 浏览器语音引擎）将文本合成为 mp3 音频流。
    完全免费、无需 API Key，音色质量接近 Azure 付费神经语音。
    """
    if not text or not text.strip():
        return JSONResponse(status_code=400, content={"code": 400, "message": "文本不能为空"})

    # 文本截断，避免过长
    text = text.strip()[:2000]

    # 校验音色是否在允许列表中
    allowed = {v["short_name"] for v in EDGE_TTS_VOICES}
    if voice not in allowed:
        voice = "zh-CN-XiaoxiaoNeural"

    try:
        import edge_tts
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"code": 503, "message": "TTS 服务未安装 edge-tts 依赖，请联系管理员"},
        )

    async def audio_stream():
        communicate = edge_tts.Communicate(text, voice, rate="+0%", pitch="+0Hz")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(
        audio_stream(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "Accept-Ranges": "none",
        },
    )


# ==================== 工具函数 ====================

def _build_user_profile(user: User) -> dict:
    """
    从登录态取出导员可用的学生身份信息（姓名 / 院系班级）。

    仅供 system prompt 用于称呼同学，不额外落地存储。
    """
    return {
        "name": (user.real_name or user.username or "").strip(),
        "department": (user.department or "").strip(),
    }


def _load_history(db: Session, session_id: Optional[str]) -> Optional[List[dict]]:
    """加载会话历史（取最近的 20 条，供多轮上下文）"""
    if not session_id:
        return None
    msgs = (
        db.query(CounselorMessage)
        .filter(CounselorMessage.session_id == session_id)
        .order_by(CounselorMessage.created_at.desc(), CounselorMessage.id.desc())
        .limit(20).all()
    )
    if not msgs:
        return None
    msgs.reverse()  # 倒序取最近 20 条后翻回时间正序，保证喂给模型的是最近的上下文
    return [{"role": m.role, "content": m.content} for m in msgs]


# 跨会话记忆最多取该用户最近多少条消息（配成约 4 轮问答）
CROSS_SESSION_MEMORY_MESSAGES = 8


def _load_cross_session_memory(
    db: Session, user_id: int, current_session_id: Optional[str],
) -> Optional[List[dict]]:
    """
    加载跨会话记忆：同一用户在其他会话里的最近若干轮问答。

    只取最近 8 条消息并截断，避免历史记忆挤占 prompt 预算；
    当前会话的内容不在此列（已由 chat_history 提供）。
    """
    query = (
        db.query(CounselorMessage)
        .join(CounselorSession, CounselorSession.id == CounselorMessage.session_id)
        .filter(CounselorSession.user_id == user_id)
    )
    if current_session_id:
        query = query.filter(CounselorMessage.session_id != current_session_id)

    msgs = query.order_by(
        CounselorMessage.created_at.desc(), CounselorMessage.id.desc(),
    ).limit(CROSS_SESSION_MEMORY_MESSAGES).all()
    if not msgs:
        return None
    msgs.reverse()

    def _date(msg) -> str:
        return msg.created_at.strftime("%m-%d") if msg.created_at else ""

    turns: List[dict] = []
    pending_question = None
    for msg in msgs:
        if msg.role == "user":
            pending_question = msg
        elif pending_question is not None:
            turns.append({
                "question": pending_question.content,
                "answer": msg.content,
                "date": _date(pending_question) or _date(msg),
            })
            pending_question = None
    # 末尾只剩提问、没有回答的，也保留下来避免丢信息
    if pending_question is not None:
        turns.append({
            "question": pending_question.content, "answer": "", "date": _date(pending_question),
        })
    return turns or None


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _generate_session_id() -> str:
    return f"csess_{uuid_lib.uuid4().hex[:16]}"


def _get_security_level(role_code: str) -> int:
    """
    根据用户角色码确定可访问的文档密级上限
    与智能问答（/chat）保持一致：
        1 = 公开, 2 = 内部, 3 = 机密, 4 = 绝密
    super_admin/knowledge_admin → 4
    dept_admin                 → 3
    employee 及未知            → 1
    """
    if role_code in ("super_admin", "knowledge_admin"):
        return 4
    if role_code == "dept_admin":
        return 3
    return 1
