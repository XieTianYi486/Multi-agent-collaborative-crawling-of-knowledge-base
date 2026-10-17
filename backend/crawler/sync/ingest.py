"""入库同步器：爬虫文档 → 知识库主库。

完全复用 backend/seed_documents.py 已验证的入库范式：
  建 KB Document 行 → commit → 同步调 _process_document_task
  → 置 review_status=2 + status=1（缺此步 ChatService._visible_doc_ids
  会拦截全部爬取内容，员工检索不到）。

幂等设计（重复运行零副作用）：
- 闸门①：KB documents.source_hash == crawl_doc.url_hash 则跳过；
- 闸门②：爬虫侧 kb_syncs.doc_id 唯一索引（每篇只推一次）。
单文档异常 → KB 文档置 status=3 + kb_syncs 记 failed，继续下一文档。

要求：脚本在 backend/ 目录下运行（app.* 依赖 sys.path 与 .env 的 cwd 约定）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..settings import DATA_DIR
from ..store import repo
from ..store.db import session_scope
from ..store.models import Document as CrawlDocument

log = logging.getLogger(__name__)

# ==================== 分类树 ====================
# (name, parent_name, sort_order, description)；parent_name="" 表示根节点
# 注意：父分类必须出现在子分类之前（ensure_crawl_categories 按序解析 parent_id）
CRAWL_CATEGORIES = [
    # ===== AI热点追踪（二级分类细化，根节点在库中已存在）=====
    ("AI热点追踪", "", 0, "AI 前沿热点追踪（论文/新闻/行业动态）"),
    ("大模型前沿", "AI热点追踪", 1, "大语言模型/生成式 AI 前沿研究"),
    ("机器学习与算法", "AI热点追踪", 2, "机器学习理论与算法研究"),
    ("计算机视觉与多模态", "AI热点追踪", 3, "视觉、多模态模型研究"),
    ("智能体与强化学习", "AI热点追踪", 4, "智能体、强化学习与决策研究"),
    ("语音技术", "AI热点追踪", 5, "语音识别/合成/音频 AI"),
    ("代码智能", "AI热点追踪", 6, "AI 编程、代码生成与软件工程 AI"),
    ("AI 安全与伦理", "AI热点追踪", 7, "AI 安全、对齐与伦理"),
    ("AI 行业动态", "AI热点追踪", 8, "AI 行业新闻、动态与产业报告"),
    # ===== 嵌入式开发（细化到三级）=====
    ("嵌入式开发", "", 4, "ESP32/树莓派/嵌入式开发教学资料（爬虫自动入库）"),
    ("ESP32", "嵌入式开发", 1, "乐鑫 ESP32 系列芯片与开发板资料"),
    ("芯片与模组资料", "ESP32", 1, "ESP32 芯片数据手册、技术文档（乐鑫官网）"),
    ("硬件问题讨论", "ESP32", 2, "ESP32 硬件设计、电路问题的社区讨论"),
    ("教程与书籍", "ESP32", 3, "ESP32 入门教程、配套书籍讨论"),
    ("论坛讨论", "ESP32", 4, "ESP32 芯片通用社区讨论"),
    ("ESP-IDF", "嵌入式开发", 2, "乐鑫 ESP-IDF 开发框架文档"),
    ("快速入门", "ESP-IDF", 1, "ESP-IDF 安装、环境搭建与入门教程"),
    ("API 参考", "ESP-IDF", 2, "ESP-IDF API 参考手册"),
    ("开发指南", "ESP-IDF", 3, "ESP-IDF 开发指南（外设/网络/存储等）"),
    ("迁移指南", "ESP-IDF", 4, "ESP-IDF 版本迁移指南"),
    ("安全与加密", "ESP-IDF", 5, "ESP-IDF 安全特性（加密/安全启动）"),
    ("论坛讨论", "ESP-IDF", 6, "ESP-IDF 中文讨论版帖子"),
    ("文档反馈", "ESP-IDF", 7, "中文文档讨论版反馈"),
    ("树莓派", "嵌入式开发", 3, "树莓派开发资料"),
    ("电子电路", "嵌入式开发", 4, "电子电路与硬件设计"),
    ("无线通信与协议", "嵌入式开发", 5, "Wi-Fi/蓝牙/Mesh/AT 等无线通信技术"),
    ("Wi-Fi", "无线通信与协议", 1, "Wi-Fi 通信技术"),
    ("蓝牙与 BLE", "无线通信与协议", 2, "蓝牙/BLE 通信技术"),
    ("Mesh 组网", "无线通信与协议", 3, "ESP-Mesh 组网技术"),
    ("AT 指令集", "无线通信与协议", 4, "ESP-AT 指令集"),
    ("网络协议栈", "无线通信与协议", 5, "TCP/IP、MQTT、HTTP 等协议栈"),
    ("物联网云平台", "嵌入式开发", 6, "阿里云/AWS/腾讯云等物联网平台接入"),
    ("AI 边缘应用", "嵌入式开发", 7, "ESP32 边缘 AI 应用（音频/视觉/语音）"),
    ("音频开发（ESP-ADF）", "AI 边缘应用", 1, "ESP-ADF 音频开发框架"),
    ("视觉应用（ESP-WHO）", "AI 边缘应用", 2, "ESP-WHO 人脸识别与视觉应用"),
    ("语音唤醒（ESP-SkaiNet）", "AI 边缘应用", 3, "ESP-SkaiNet 语音唤醒与命令识别"),
    ("显示与交互", "嵌入式开发", 8, "ESP-BOX 等显示与触控交互"),
    ("项目案例", "嵌入式开发", 9, "开源项目展示与实战案例"),
    ("智能玩具", "项目案例", 1, "智能玩具/机器人宠物项目（喵伴等）"),
    ("生产与认证", "嵌入式开发", 10, "芯片生产支持与认证合规资料"),
    ("认证证书", "生产与认证", 1, "RoHS/CE/PSA 等认证证书"),
    ("产品变更通知", "生产与认证", 2, "PCN 产品变更通知"),
    ("安全公告", "生产与认证", 3, "官方安全公告（Advisory）"),
    ("生产支持", "生产与认证", 4, "生产问题讨论与支持"),
    ("技术社区文章", "嵌入式开发", 11, "技术社区公开分享内容"),
]

# 站点 code → 默认分类名（tagger 不可用/未打标时的规则兜底）
DEFAULT_CATEGORY_BY_SITE = {
    "espressif_docs_esp32": "ESP32",
    "espressif_doc_portal": "ESP32",
    "esp32_forum_idf": "ESP32",
    "github_espressif_esp_idf": "ESP-IDF",
    "espressif_cn_news": "ESP32",
    "espressif_cn_home": "ESP32",
    "espressif_cn_sitemap": "ESP32",
    "elecfans_wireless": "电子电路",
    "raspberrypi_blog": "树莓派",
}

FALLBACK_CATEGORY = "技术社区文章"


@dataclass
class SyncStats:
    """一次入库同步的统计结果。"""

    synced: int = 0
    skipped: int = 0
    failed: int = 0


# ==================== KB 侧准备（分类树 + 管理员，均幂等） ====================


def ensure_crawl_categories(db: Session) -> dict[str, int]:
    """确保嵌入式开发分类树存在，返回 {分类名: 分类ID}（按 name+parent 判重幂等）。"""
    from app.models.document import Category

    cat_map: dict[str, int] = {}
    for name, parent_name, sort_order, desc in CRAWL_CATEGORIES:
        parent_id = cat_map.get(parent_name, 0)
        existing = (
            db.query(Category)
            .filter(Category.name == name, Category.parent_id == parent_id)
            .first()
        )
        if existing:
            cat_map[name] = existing.id
            continue
        cat = Category(
            name=name, parent_id=parent_id, sort_order=sort_order, description=desc
        )
        db.add(cat)
        db.flush()
        db.refresh(cat)
        cat_map[name] = cat.id
    db.commit()
    return cat_map


def ensure_admin(db: Session) -> int:
    """确保 4 个预置角色与 admin 管理员存在（爬虫入库以 admin 为 created_by）。"""
    from app.core.security import hash_password
    from app.models.user import Role, User

    default_roles = [
        ("超级管理员", "super_admin", "拥有系统全部权限", ["*"]),
        ("知识库管理员", "knowledge_admin", "管理文档和知识库内容",
         ["documents:*", "categories:*", "logs:read", "stats:read"]),
        ("部门管理员", "dept_admin", "管理部门文档和问答统计",
         ["documents:read", "stats:read"]),
        ("普通员工", "employee", "查询知识库文档",
         ["chat:ask", "documents:read"]),
    ]
    for name, code, desc, perms in default_roles:
        if not db.query(Role).filter(Role.code == code).first():
            db.add(Role(name=name, code=code, description=desc, permissions=perms))
    db.flush()
    super_admin_role = db.query(Role).filter(Role.code == "super_admin").first()

    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            real_name="系统管理员",
            email="admin@company.com",
            department="人力资源部",
            role_id=super_admin_role.id,
            status=1,
        )
        db.add(admin)
        db.flush()
        db.refresh(admin)
        db.commit()
        log.info("已创建管理员用户 admin（爬虫入库使用）")
    return admin.id


# ==================== 同步主入口 ====================


def sync_documents(limit: int = 100) -> SyncStats:
    """把待同步的爬虫文档入库知识库主库（逐文档容错，幂等）。"""
    stats = SyncStats()
    with session_scope() as session:
        docs = repo.unsynced_documents(session, limit)
        if not docs:
            return stats
        kb_db = _kb_session()
        try:
            category_map = ensure_crawl_categories(kb_db)
            admin_id = ensure_admin(kb_db)
            for doc in docs:
                _sync_one(session, kb_db, doc, category_map, admin_id, stats)
        finally:
            kb_db.close()
    log.info("知识库同步完成：成功 %d，跳过 %d，失败 %d",
             stats.synced, stats.skipped, stats.failed)
    return stats


def _kb_session() -> Session:
    """打开知识库主库会话（延迟导入：app.* 依赖 backend/ 在 sys.path 与 cwd）。"""
    from app.db.sqlite import SessionLocal

    return SessionLocal()


def _sync_one(
    session: Session,
    kb_db: Session,
    crawl_doc: CrawlDocument,
    category_map: dict[str, int],
    admin_id: int,
    stats: SyncStats,
) -> None:
    """单文档同步（幂等闸门 → 组装 md → 建 KB Document → 入库 → 自动过审 → 留痕）。"""
    from app.models.document import Document as KbDocument

    # 幂等闸门①：KB 侧 source_hash 已存在 → 跳过
    existing = (
        kb_db.query(KbDocument)
        .filter(KbDocument.source_hash == crawl_doc.url_hash)
        .first()
    )
    if existing:
        repo.mark_kb_synced(
            session, doc_id=crawl_doc.id, kb_doc_id=existing.id,
            title=crawl_doc.title, status="ok", error="KB 侧 source_hash 已存在",
        )
        stats.skipped += 1
        return

    # 智能体结论：审核拦截 / 与教学领域无关 → 跳过
    if crawl_doc.review_pass is False:
        repo.mark_kb_synced(
            session, doc_id=crawl_doc.id, title=crawl_doc.title,
            status="skipped", error=f"审核拦截: {crawl_doc.review_reason[:200]}",
        )
        stats.skipped += 1
        log.info("审核拦截，跳过入库: %s（%s）", crawl_doc.title[:60], crawl_doc.review_reason[:80])
        return
    if crawl_doc.relevant is False:
        repo.mark_kb_synced(
            session, doc_id=crawl_doc.id, title=crawl_doc.title,
            status="skipped", error="打标判定与教学领域无关",
        )
        stats.skipped += 1
        return

    try:
        kb_doc_id = _create_kb_document(kb_db, crawl_doc, category_map, admin_id)
    except Exception as exc:  # noqa: BLE001 - 单文档失败不影响其他文档
        kb_db.rollback()
        repo.mark_kb_synced(
            session, doc_id=crawl_doc.id, title=crawl_doc.title,
            status="failed", error=f"入库失败: {type(exc).__name__}: {exc}",
        )
        stats.failed += 1
        log.error("爬虫文档入库失败 %s: %s", crawl_doc.url, exc)
        return

    repo.mark_kb_synced(
        session, doc_id=crawl_doc.id, kb_doc_id=kb_doc_id, title=crawl_doc.title
    )
    stats.synced += 1


def _create_kb_document(
    kb_db: Session,
    crawl_doc: CrawlDocument,
    category_map: dict[str, int],
    admin_id: int,
) -> int:
    """组装 Markdown → 建 KB Document 行 → 入库 → 自动过审。返回 KB 文档 ID。"""
    from app.core.config import settings as kb_settings
    from app.models.document import Document as KbDocument

    # 1. 组装 Markdown 并复制到 UPLOAD_DIR（文件名哈希化规避 Windows 路径问题）
    md_content = _build_markdown(crawl_doc)
    stored_name = f"crawl_{crawl_doc.content_hash}.md"
    dest_path = Path(kb_settings.UPLOAD_DIR) / stored_name
    dest_path.write_text(md_content, encoding="utf-8")

    # 2. 分类：tagger 打标结果 → 站点默认分类 → 兜底分类
    site = crawl_doc.site
    category_name = crawl_doc.category or DEFAULT_CATEGORY_BY_SITE.get(site.code, "")
    category_id = category_map.get(category_name) or category_map.get(FALLBACK_CATEGORY)

    # 3. 创建 KB Document 行
    doc = KbDocument(
        title=crawl_doc.title[:255],
        file_name=stored_name,
        file_path=str(dest_path),
        file_size=dest_path.stat().st_size,
        file_type="md",
        category_id=category_id,
        tags=list(crawl_doc.keywords or [])[:10],
        security_level=1,  # 公开技术资料，employee 可见
        status=0,  # 处理中
        created_by=admin_id,
        publish_date=date.today(),
        source_url=crawl_doc.url,
        source_hash=crawl_doc.url_hash,
    )
    kb_db.add(doc)
    kb_db.flush()
    kb_db.refresh(doc)
    kb_db.commit()  # 必须先提交，_process_document_task 用独立 session

    # 4. 入库：解析 → 分块 → 向量化 → ChromaDB + BM25 + DocChunk
    from app.tasks.document_tasks import _process_document_task

    try:
        _process_document_task(doc.id)
    except Exception:
        # 处理失败（如 embedding 不可用）→ 标记失败状态后继续抛给上层留痕
        kb_db.rollback()
        doc = kb_db.query(KbDocument).filter(KbDocument.id == doc.id).first()
        if doc:
            doc.status = 3
            kb_db.commit()
        raise

    # 5. 自动过审发布（公开技术资料；缺此步可见性过滤会拦截全部爬取内容）
    doc = kb_db.query(KbDocument).filter(KbDocument.id == doc.id).first()
    doc.review_status = 2
    doc.reviewed_by = admin_id
    doc.reviewed_at = datetime.now()
    doc.review_comment = (
        f"爬虫自动入库：来源 {crawl_doc.url}；"
        f"{site.risk_level}风险源；仅校内教学使用，自动审核通过"
    )
    doc.status = 1
    kb_db.commit()
    log.info("入库成功 [KB#%d]: %s", doc.id, crawl_doc.title[:60])
    return doc.id


def _build_markdown(crawl_doc: CrawlDocument) -> str:
    """组装入库 Markdown：来源注记头 + 正文（全文 md 文件优先，节选源带原文链接）。"""
    meta = crawl_doc.meta_json or {}
    header_lines = [
        f"# {crawl_doc.title}",
        "",
        f"- 来源：{crawl_doc.url}",
        f"- 采集时间：{crawl_doc.fetched_at:%Y-%m-%d}",
    ]
    if crawl_doc.author:
        header_lines.append(f"- 作者：{crawl_doc.author}")
    if meta.get("license_note"):
        header_lines.append(f"- 授权说明：{meta['license_note']}")
    header_lines.append("")
    header = "\n".join(header_lines)

    # 低风险源：全文 Markdown 文件
    if crawl_doc.content_md_path:
        md_path = DATA_DIR / crawl_doc.content_md_path
        if md_path.exists():
            return header + md_path.read_text(encoding="utf-8")

    # 中风险源：节选 + 原文链接
    body = crawl_doc.text or ""
    if crawl_doc.license_status != "low":
        body = f"{body}\n\n> 本文为节选，完整内容见原文：{crawl_doc.url}"
    return header + body
