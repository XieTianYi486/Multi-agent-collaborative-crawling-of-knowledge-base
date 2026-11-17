"""补采需求自动闭环：发现式采集入库并同步到知识库后，关闭对应需求并通知提交人。

与 collection_service.auto_complete_requests（关键词匹配兜底）互补：
这里靠 discovery_queue.request_id 显式绑定，不会误判。
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from ..store.db import session_scope
from ..store.models import DiscoveryQueue, KnowledgeBaseSync

log = logging.getLogger(__name__)


def resolve_requests(attempted_ids: Optional[Iterable[int]] = None) -> tuple[int, int]:
    """关闭补采需求，返回 (成功入库条数, 未匹配资料条数)。

    - 已入库：status 1 → 2
    - 本轮尝试过、但没有抓到可入库资料：status 1 → 4（未匹配资料）
    只处理 attempted_ids 里的需求，避免把本轮没跑到的需求误判为失败。
    """
    # request_id → [(候选标题, KB 文档 ID)]：全部已同步文档都参与主题校验，
    # 不能只看任意一行（一行不相关不代表本轮抓到的其他资料也不相关）
    success: dict[int, list[tuple[str, Optional[int]]]] = {}
    dead: dict[int, str] = {}

    with session_scope() as session:
        attempted = [i for i in dict.fromkeys(attempted_ids or [])]
        if attempted:
            rows = (
                session.query(DiscoveryQueue, KnowledgeBaseSync)
                .join(KnowledgeBaseSync, KnowledgeBaseSync.doc_id == DiscoveryQueue.doc_id)
                .filter(
                    DiscoveryQueue.request_id.in_(attempted),
                    DiscoveryQueue.status == "fetched",
                    DiscoveryQueue.doc_id.isnot(None),
                    KnowledgeBaseSync.status == "ok",
                    KnowledgeBaseSync.kb_doc_id.isnot(None),
                )
                .all()
            )
            for item, _sync in rows:
                success.setdefault(item.request_id, []).append(
                    (item.title, _sync.kb_doc_id)
                )

        ids = [i for i in attempted if i not in success]
        if ids:
            queue_rows = (
                session.query(DiscoveryQueue)
                .filter(DiscoveryQueue.request_id.in_(ids))
                .all()
            )
            doc_ids = [r.doc_id for r in queue_rows if r.doc_id]
            syncs: dict[int, KnowledgeBaseSync] = {}
            if doc_ids:
                syncs = {
                    s.doc_id: s
                    for s in session.query(KnowledgeBaseSync)
                    .filter(KnowledgeBaseSync.doc_id.in_(doc_ids))
                    .all()
                }
            by_request: dict[int, list[DiscoveryQueue]] = {}
            for row in queue_rows:
                by_request.setdefault(row.request_id, []).append(row)

            for request_id in ids:
                items = by_request.get(request_id, [])
                if _still_pending(items, syncs):
                    continue  # 还有候选没抓完/没同步完，留到下一轮
                dead[request_id] = _dead_reason(items, syncs)

    if not success and not dead:
        return 0, 0

    from app.db.sqlite import SessionLocal
    from app.models.collection import CollectionRequest
    from app.models.document import Document
    from app.services.collection_service import is_relevant
    from app.services.notification_service import notify

    completed = 0
    unmatched = 0
    db = SessionLocal()
    try:
        for request_id, candidates in success.items():
            req = db.query(CollectionRequest).filter(CollectionRequest.id == request_id).first()
            if req is None or req.status != 1:
                continue
            # 主题校验：抓到资料不等于覆盖需求（如 FastAPI 需求抓到《Python 教程》）。
            # 逐篇检查全部候选，任一相关即认为覆盖；全部不相关才标记未匹配。
            matched_title = None
            for title, kb_doc_id in candidates:
                doc = (
                    db.query(Document).filter(Document.id == kb_doc_id).first()
                    if kb_doc_id else None
                )
                if doc is not None and is_relevant(req.question, doc):
                    matched_title = title
                    break

            if matched_title is None:
                best = (candidates[0][0] if candidates else "") or ""
                req.status = 4
                req.note = f"采集到的资料《{best[:60]}》与需求主题不符，可稍后重新提交。"
                notify(
                    db,
                    req.created_by,
                    "collection",
                    "补采暂未匹配到主题资料",
                    f"你提交的「{req.question[:40]}」本轮抓到的资料与需求主题不符，暂未收录。",
                    "/my-collections",
                )
                unmatched += 1
                continue
            req.status = 2
            req.note = (
                f"已补采《{matched_title[:80]}》，等待管理员审核发布"
                if matched_title else "已补采到资料，等待管理员审核发布"
            )
            notify(
                db,
                req.created_by,
                "collection",
                "补采需求已采集到资料",
                f"你提交的「{req.question[:40]}」已补采到资料「{matched_title[:60]}」，"
                "管理员审核通过后即可在知识库检索到。",
                "/my-collections",
            )
            completed += 1

        for request_id, reason in dead.items():
            req = db.query(CollectionRequest).filter(CollectionRequest.id == request_id).first()
            if req is None or req.status != 1:
                continue
            req.status = 4
            req.note = f"{reason}，可稍后重新提交或联系老师补充。"
            notify(
                db,
                req.created_by,
                "collection",
                "补采暂未匹配到资料",
                f"你提交的「{req.question[:40]}」本轮未找到可入库的资料（{reason}）。",
                "/my-collections",
            )
            unmatched += 1
        db.commit()
    finally:
        db.close()

    if completed or unmatched:
        log.info("补采需求闭环：完成 %d 条，未匹配 %d 条", completed, unmatched)
    return completed, unmatched


def _still_pending(
    items: list[DiscoveryQueue], syncs: dict[int, KnowledgeBaseSync]
) -> bool:
    """队列里还有未终结的候选（等待抓取，或已抓取但本轮还没同步）。"""
    for item in items:
        if item.status == "queued":
            return True
        if item.status == "fetched" and item.doc_id and item.doc_id not in syncs:
            return True
    return False


def _dead_reason(
    items: list[DiscoveryQueue], syncs: dict[int, KnowledgeBaseSync]
) -> str:
    if not items or all(i.channel == "scout" for i in items):
        # scout 哨兵行（none:// 前缀）表示本轮侦察确实没有可用候选
        return "未检索到可用资料"
    if any(item.status == "failed" for item in items):
        return "候选页面抓取失败"
    if any(_sync_status(syncs, item) == "skipped" for item in items):
        return "抓取到的内容与教学领域无关"
    if any(_sync_status(syncs, item) == "failed" for item in items):
        return "资料入库失败"
    return "未找到可入库的资料"


def _sync_status(
    syncs: dict[int, KnowledgeBaseSync], item: DiscoveryQueue
) -> Optional[str]:
    sync = syncs.get(item.doc_id) if item.doc_id else None
    return sync.status if sync else None
