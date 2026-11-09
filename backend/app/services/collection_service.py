# ============================================================
# 补采需求 <-> 文档 自动匹配
# 文档审核通过后，用标题/标签/分类与需求问题做关键词匹配，
# 命中则自动把「已触发」需求标记为「已完成」。
# ============================================================

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.collection import CollectionRequest
from app.models.document import Document
from app.services.notification_service import notify

# 只剔除疑问/虚词二元组，保留「定时」「摄像」等实义词
CN_STOP_BIGRAMS = {
    "如何", "怎么", "怎样", "什么", "为什", "是否", "可以", "能否",
    "请问", "一下", "哪些", "哪个", "多少", "以及", "区别", "比较",
    "介绍", "使用", "配置", "方法", "实现", "支持", "需要", "时候",
    "问题", "进行", "我们", "这个", "那个", "现在", "为何", "有什",
    "的是", "了吗", "呢", "吗", "么",
}

ASCII_RE = re.compile(r"[a-z0-9][a-z0-9\-_.+/]{2,}")
CN_RE = re.compile(r"[\u4e00-\u9fff]+")


def _ascii_terms(text: str) -> set[str]:
    return {t for t in ASCII_RE.findall((text or "").lower()) if len(t) >= 3}


def _cn_ngrams(text: str, size: int) -> set[str]:
    grams: set[str] = set()
    for seg in CN_RE.findall((text or "").lower()):
        for i in range(len(seg) - size + 1):
            gram = seg[i:i + size]
            if gram not in CN_STOP_BIGRAMS:
                grams.add(gram)
    return grams


def is_relevant(question: str, doc: Document) -> bool:
    """判断文档是否可能覆盖补采问题。

    规则（满足其一）：
    - 命中文档中的英文/数字术语（ESP32、BME280、I2C 等，长度 >= 3）
    - 命中 1 个中文三元组且同时命中 2 个二元组
    - 命中 >= 3 个中文二元组
    """
    if not question or not doc:
        return False

    category = doc.category.name if getattr(doc, "category", None) else ""
    haystack = " ".join([
        doc.title or "",
        doc.tags or "",
        category or "",
        (doc.summary or "") if hasattr(doc, "summary") else "",
    ]).lower()

    if any(term in haystack for term in _ascii_terms(question)):
        return True

    q_bigrams = _cn_ngrams(question, 2)
    h_bigrams = _cn_ngrams(haystack, 2)
    matched_bigrams = len(q_bigrams & h_bigrams)
    if matched_bigrams >= 3:
        return True

    q_trigrams = _cn_ngrams(question, 3)
    h_trigrams = _cn_ngrams(haystack, 3)
    return matched_bigrams >= 2 and bool(q_trigrams & h_trigrams)


def auto_complete_requests(db: Session, doc: Document) -> int:
    """文档审核通过后，自动完成匹配的「已触发」补采需求，返回完成数量。"""
    if not doc or doc.review_status != 2:
        return 0

    requests = (
        db.query(CollectionRequest)
        .filter(CollectionRequest.status == 1)
        .all()
    )
    completed = 0
    for req in requests:
        if not is_relevant(req.question, doc):
            continue
        req.status = 2
        req.note = f"已自动关联文档《{doc.title}》"
        notify(
            db,
            req.created_by,
            "collection",
            "补采需求已完成",
            f"你提交的补采「{req.question[:40]}」已由文档《{doc.title}》覆盖。",
            "/my-collections",
        )
        completed += 1

    if completed:
        db.commit()
    return completed
