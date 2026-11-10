# ============================================================
# AI 助手 · 资料检索
#
# 把"帮我找 XX 课件 / 有没有 XX 视频"这类自然语言需求，
# 转成知识库里真实存在的文档与视频条目，交由前端渲染成卡片并一键跳转，
# 让助手不止能问答，还能直接把人带到资料所在页面。
# ============================================================

import re
from typing import Dict, List
from urllib.parse import quote

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.video import Video

# 出现这些词才认为用户在"找资料"，避免普通概念提问被塞一堆卡片
_INTENT_WORDS = (
    "帮我找", "帮我搜", "帮找", "找一下", "找一找", "有没有", "搜一下", "搜索",
    "推荐", "资料", "文档", "课件", "讲义", "习题", "试题", "案例", "教程",
    "视频", "ppt", "大纲", "实验",
)

# 提取检索词时剥离的噪声词（否则"帮我""相关"会变成无效关键词）
_NOISE_WORDS = (
    "帮我找", "帮我搜", "帮我", "请帮", "麻烦", "我想", "想要", "有没有",
    "有哪些", "哪些", "什么", "怎么样", "怎么", "如何", "找一下", "找一找",
    "搜一下", "搜索", "查找", "找", "搜", "推荐", "相关", "一下", "关于",
    "资料", "文档", "课件", "讲义", "视频", "教程", "的", "和", "与",
)

_SPLIT_RE = re.compile(r"[\s,，。.？?！!、；;：:（）()【】\[\]\"'“”‘’/\\|]+")

MAX_DOCUMENTS = 4
MAX_VIDEOS = 3


def _has_intent(question: str) -> bool:
    text = (question or "").lower()
    return any(word in text for word in _INTENT_WORDS)


def _keywords(question: str) -> List[str]:
    """从问句中提取检索关键词（去噪后按标点切分，保留长度>=2 的片段）"""
    text = question or ""
    for word in _NOISE_WORDS:
        text = text.replace(word, " ")
    tokens: List[str] = []
    for token in _SPLIT_RE.split(text):
        token = token.strip()
        if len(token) >= 2 and token.lower() not in [t.lower() for t in tokens]:
            tokens.append(token)
    return tokens[:5]


def _score(text: str, keywords: List[str]) -> int:
    """标题命中关键词越多越靠前，标题越短越精确"""
    lowered = (text or "").lower()
    hit = sum(1 for kw in keywords if kw.lower() in lowered)
    return hit * 100 - len(text or "")


def _search_documents(
    db: Session, keywords: List[str], security_level: int
) -> List[Dict]:
    conditions = [Document.title.like(f"%{kw}%") for kw in keywords]
    docs = (
        db.query(Document)
        .filter(
            Document.status == 1,              # 已发布
            Document.review_status == 2,       # 审核通过
            Document.security_level <= security_level,
            or_(*conditions),
        )
        .limit(40)
        .all()
    )
    docs.sort(key=lambda d: _score(d.title, keywords), reverse=True)
    return [
        {
            "type": "document",
            "id": doc.id,
            "title": doc.title,
            "subtitle": f"{doc.file_type.upper()} · {doc.category.name if doc.category else '未分类'}",
            "file_type": doc.file_type,
            # 跳转到文档页并按标题检索，用户落地即可看到目标资料
            "url": f"/documents?keyword={quote(doc.title)}",
        }
        for doc in docs[:MAX_DOCUMENTS]
    ]


def _search_videos(db: Session, keywords: List[str]) -> List[Dict]:
    conditions = []
    for kw in keywords:
        pattern = f"%{kw}%"
        conditions.extend([
            Video.title.like(pattern),
            Video.description.like(pattern),
            Video.category.like(pattern),
        ])
    videos = (
        db.query(Video)
        .filter(Video.status == 1, or_(*conditions))
        .limit(30)
        .all()
    )
    videos.sort(key=lambda v: _score(v.title, keywords), reverse=True)
    return [
        {
            "type": "video",
            "id": video.id,
            "title": video.title,
            "subtitle": " · ".join(
                part for part in (video.up_name, video.category, video.difficulty) if part
            ),
            "file_type": "video",
            "url": f"/videos?keyword={quote(video.title)}",
        }
        for video in videos[:MAX_VIDEOS]
    ]


def search_resources(
    db: Session, question: str, security_level: int = 1
) -> List[Dict]:
    """
    根据问句检索可跳转的资料条目。

    非资料类提问（如"什么是中断"）返回空列表，保持纯问答体验；
    检索异常不影响问答主流程，由调用方兜底。
    """
    if not _has_intent(question):
        return []
    keywords = _keywords(question)
    if not keywords:
        return []

    resources: List[Dict] = []
    try:
        documents = _search_documents(db, keywords, security_level)
        videos = _search_videos(db, keywords)
        # 用户明确说"视频"时视频置顶，说"课件/文档/讲义"时文档置顶
        if "视频" in question:
            resources = videos + documents
        else:
            resources = documents + videos
    except Exception:
        return []
    return resources
