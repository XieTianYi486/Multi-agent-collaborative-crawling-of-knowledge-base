"""批量导入压缩包爬取数据文档（一次性回填脚本）。

用法（在 backend/ 目录下运行；导入前先停 uvicorn，避免 ChromaDB 并发写）：
  python import_crawl_zip.py                  # 解压 + 导入 + AI热点追踪存量重归类
  python import_crawl_zip.py --limit 10       # 冒烟测试：只导入前 10 篇
  python import_crawl_zip.py --dry-run        # 只统计分类分布，不写库
  python import_crawl_zip.py --only-reclassify  # 只做存量重归类
  python import_crawl_zip.py --zip <path>     # 指定压缩包路径

zip 结构（内部文件名 GBK 编码，需 cp437→gbk 修正）：
  新建文件夹/esp32_forum/<版面>/<tid>_<标题>.md     论坛帖（帖头含「原文链接」）
  新建文件夹/esp_idf_zh_esp32/<章节>/<页面>.md       ESP-IDF 中文编程指南
  新建文件夹/espressif_docs/<子目录>/<TCD号>.md     乐鑫官网技术文档

入库范式复用 crawler/sync/ingest.py 的已验证路径：
  建 KB Document 行 → process_document（解析→分块→向量化→Chroma+BM25）
  → 写 DocChunk 行 → review_status=2 + status=1 自动过审。
幂等：source_hash = sha256("zip_import:" + 压缩包内相对路径)，重复运行跳过。
BM25 索引全量结束后统一持久化一次（process_document(persist_index=False)）。
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# 脚本须在 backend/ 目录下运行（app.* / crawler.* 依赖 cwd 与 .env 约定）
BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.sqlite import SessionLocal  # noqa: E402
from app.models.document import Category, DocChunk, Document  # noqa: E402
from app.rag.ingestion import process_document  # noqa: E402
from app.rag.retrievers.bm25_retriever import save_bm25_index  # noqa: E402
from crawler.sync.ingest import ensure_admin, ensure_crawl_categories  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("import_crawl_zip")

DEFAULT_ZIP = r"E:\Claude_Project_second\爬取数据文档.zip"
ZIP_ROOT = "新建文件夹"  # 压缩包顶层目录（GBK 解码后）
IMPORT_SUBDIR = "import_20260919"  # uploads 下的导入目录

# ==================== 路径 → 分类映射 ====================
# 分类路径为 categories 表的名称链（根 → 子 → 孙），与 CRAWL_CATEGORIES 一致

# 论坛版面 → 分类路径
BOARD_CATEGORY: dict[str, tuple[str, ...]] = {
    "ESP-IDF 中文讨论版": ("嵌入式开发", "ESP-IDF", "论坛讨论"),
    "ESP-AT 中文讨论版": ("嵌入式开发", "无线通信与协议", "AT 指令集"),
    "ESP Mesh 中文讨论版": ("嵌入式开发", "无线通信与协议", "Mesh 组网"),
    "ESP IoT Solution 中文讨论版": ("嵌入式开发", "物联网云平台"),
    "ESP Cloud 中文讨论版": ("嵌入式开发", "物联网云平台"),
    "ESP-WHO 中文讨论版": ("嵌入式开发", "AI 边缘应用", "视觉应用（ESP-WHO）"),
    "ESP-SkaiNet 中文讨论版": ("嵌入式开发", "AI 边缘应用", "语音唤醒（ESP-SkaiNet）"),
    "ESP-ADF 中文讨论版": ("嵌入式开发", "AI 边缘应用", "音频开发（ESP-ADF）"),
    "ESP-BOX 中文讨论版": ("嵌入式开发", "显示与交互"),
    "硬件问题讨论": ("嵌入式开发", "ESP32", "硬件问题讨论"),
    "项目展示": ("嵌入式开发", "项目案例"),
    "喵伴 中文讨论版": ("嵌入式开发", "项目案例", "智能玩具"),
    "《ESP32-C3 物联网工程开发实战》书籍讨论版": ("嵌入式开发", "ESP32", "教程与书籍"),
    "中文文档讨论版": ("嵌入式开发", "ESP-IDF", "文档反馈"),
    "ESP 生产支持讨论版": ("嵌入式开发", "生产与认证", "生产支持"),
    "ESP32-S31 中文讨论版": ("嵌入式开发", "ESP32", "论坛讨论"),
}

# ESP-IDF 中文编程指南一级章节 → 分类路径
IDF_SECTION_CATEGORY: dict[str, tuple[str, ...]] = {
    "get-started": ("嵌入式开发", "ESP-IDF", "快速入门"),
    "api-reference": ("嵌入式开发", "ESP-IDF", "API 参考"),
    "api-guides": ("嵌入式开发", "ESP-IDF", "开发指南"),
    "migration-guides": ("嵌入式开发", "ESP-IDF", "迁移指南"),
    "security": ("嵌入式开发", "ESP-IDF", "安全与加密"),
    "hw-reference": ("嵌入式开发", "ESP32", "芯片与模组资料"),
    "libraries-and-frameworks": ("嵌入式开发", "ESP-IDF", "开发指南"),
    "third-party-tools": ("嵌入式开发", "ESP-IDF", "开发指南"),
    "contribute": ("嵌入式开发", "ESP-IDF", "开发指南"),
}

# 乐鑫官网文档子目录 → 分类路径
ESPRESSIF_DIR_CATEGORY: dict[str, tuple[str, ...]] = {
    "Technical Documents": ("嵌入式开发", "ESP32", "芯片与模组资料"),
    "Certificate": ("嵌入式开发", "生产与认证", "认证证书"),
    "PCN": ("嵌入式开发", "生产与认证", "产品变更通知"),
    "Advisory": ("嵌入式开发", "生产与认证", "安全公告"),
}

FALLBACK_PATH = ("嵌入式开发", "技术社区文章")

# ==================== zip 文件名 GBK 修正 ====================


def decode_zip_name(name: str) -> str:
    """zip 内文件名按 GBK 存储但被 zipfile 按 cp437 读出，转回 GBK。"""
    try:
        return name.encode("cp437").decode("gbk")
    except Exception:  # noqa: BLE001 - 已是合法 Unicode 则原样返回
        return name


# ==================== 扫描与解压 ====================


def scan_md_items(zip_path: str) -> list[dict]:
    """扫描压缩包内的 md 文档（跳过附件/图片/json），返回条目列表。"""
    items = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = decode_zip_name(info.filename)
            parts = name.split("/")
            if parts[0] != ZIP_ROOT or len(parts) < 3:
                continue
            if not name.endswith(".md"):
                continue
            if any(seg.endswith("_附件") or seg == "_images" for seg in parts):
                continue
            rel_path = "/".join(parts[1:])  # 去掉 新建文件夹/ 前缀
            items.append({
                "zip_name": info.filename,
                "rel_path": rel_path,
                "site": parts[1],
                "board": parts[2] if len(parts) > 3 else "",
            })
    return items


def safe_disk_relpath(rel_path: str) -> str:
    """Windows 路径过长时用哈希前缀兜底（260 字符限制）。"""
    max_len = 220
    if len(rel_path) <= max_len:
        return rel_path
    h = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:16]
    stem = Path(rel_path).stem[:80]
    parent = str(Path(rel_path).parent)
    return f"{parent}/{h}_{stem}.md"


def extract_md(zip_path: str, items: list[dict], dest_root: Path) -> dict[str, Path]:
    """把 md 条目解压到 dest_root/，返回 {rel_path: 磁盘绝对路径}。"""
    extracted: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for item in items:
            dest = dest_root / safe_disk_relpath(item["rel_path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(zf.read(item["zip_name"]))
            extracted[item["rel_path"]] = dest
    return extracted


# ==================== source_url 解析 ====================


def load_idf_url_map(dest_root: Path) -> dict[str, str]:
    """由 _crawl_progress.json 的 done URL 列表构造 {相对路径: 原文URL}。"""
    import json

    url_map: dict[str, str] = {}
    progress = dest_root / "esp_idf_zh_esp32" / "_crawl_progress.json"
    if not progress.exists():
        return url_map
    prefix = "https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/"
    try:
        data = json.loads(progress.read_text(encoding="utf-8"))
        for url in data.get("done", []):
            if not url.startswith(prefix):
                continue
            rel = url[len(prefix):]
            if rel.endswith(".html"):
                url_map[rel[:-5] + ".md"] = url
            elif rel.endswith("/"):
                url_map[rel + "index.md"] = url + "index.html"
    except Exception as exc:  # noqa: BLE001
        log.warning("解析 _crawl_progress.json 失败: %s", exc)
    return url_map


def load_espressif_url_map(dest_root: Path) -> dict[str, str]:
    """由 crawl_index.json 构造 {相对路径: 原文URL}（entries 可能带 url 字段）。"""
    import json

    url_map: dict[str, str] = {}
    index_file = dest_root / "espressif_docs" / "crawl_index.json"
    if not index_file.exists():
        return url_map
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
        for group in ("success", "failed", "skipped"):
            for entry in data.get(group, []):
                path = (entry.get("path") or "").replace("\\", "/")
                url = entry.get("url") or entry.get("link") or ""
                if path and url:
                    url_map[path] = url
    except Exception as exc:  # noqa: BLE001
        log.warning("解析 crawl_index.json 失败: %s", exc)
    return url_map


def extract_forum_url(content: str) -> str:
    """论坛帖头部「原文链接: URL」提取。"""
    m = re.search(r"原文链接[:：]\s*(https?://\S+)", content)
    return m.group(1).strip() if m else ""


def extract_forum_date(content: str) -> Optional[date]:
    """论坛帖头部「发布时间: Tue Apr 04, 2023 8:07 am」解析为日期。"""
    m = re.search(r"发布时间[:：][^\n]*?\b([A-Z][a-z]{2} \d{2}, \d{4})", content)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%b %d, %Y").date()
    except ValueError:
        return None


# ==================== 分类与标题 ====================


def category_path_for(item: dict) -> tuple[str, ...]:
    """按 站点+版面/章节 返回分类名称链（确定性规则，零 LLM 费用）。"""
    site, board = item["site"], item["board"]
    if site == "esp32_forum":
        return BOARD_CATEGORY.get(board, FALLBACK_PATH)
    if site == "esp_idf_zh_esp32":
        return IDF_SECTION_CATEGORY.get(board, ("嵌入式开发", "ESP-IDF", "开发指南"))
    if site == "espressif_docs":
        return ESPRESSIF_DIR_CATEGORY.get(board, FALLBACK_PATH)
    return FALLBACK_PATH


def resolve_category_id(db: Session, path: tuple[str, ...]) -> Optional[int]:
    """按名称链（根→子→孙）在 categories 表解析分类 ID。"""
    parent_id = 0
    for name in path:
        row = (
            db.query(Category)
            .filter(Category.name == name, Category.parent_id == parent_id)
            .first()
        )
        if row is None:
            return None
        parent_id = row.id
    return parent_id


def extract_title(content: str, rel_path: str) -> str:
    """取首个 Markdown 一级标题；无则用文件名（去掉论坛 tid_ 前缀）。"""
    m = re.search(r"^#\s+(.+?)\s*$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()[:255]
    stem = Path(rel_path).stem
    stem = re.sub(r"^\d+_", "", stem)  # 论坛文件名 "32986_标题.md" 去掉 tid
    return stem[:255]


def norm_body(text: str) -> str:
    """归一化正文用于内容去重：去首行标题/来源注记头/节选注记 + 折叠空白。

    首行标题也剥掉：KB 存量文件标题带「- ESP32 - — ...」后缀而压缩包内
    标题干净，保留首行会导致同一文档的内容哈希永不匹配。
    """
    lines = []
    for i, line in enumerate(text.splitlines()):
        if i == 0 and line.startswith("# "):
            continue
        if re.match(r"^\s*-\s*(来源|采集时间|作者|授权说明)[:：]", line):
            continue
        if line.strip().startswith("> 本文为节选"):
            continue
        lines.append(line)
    return re.sub(r"\s+", " ", "\n".join(lines)).strip()


def content_body_hash(text: str) -> str:
    """归一化正文的 SHA256（防与既有爬取结果重复）。"""
    return hashlib.sha256(norm_body(text).encode("utf-8")).hexdigest()


# ==================== 存量「AI热点追踪」重归类 ====================

# 规则：(正则, 分类路径)；按序首个命中即生效
RECLASSIFY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (r"SWE|Grep|LSP|\bCode\b|Coding|Compile|Programming", ("AI热点追踪", "代码智能")),
    (r"LLM|Language Model|Pretrain|Pre-training|Transformer|\bGPT\b|Prompt|Distill"
     r"|大模型|ChatGPT|Claude|Grok|Fable|Inference|Translation|NLP",
     ("AI热点追踪", "大模型前沿")),
    (r"Vision|VLM|Video|Pose|Image|Multimodal|Visual|Camera",
     ("AI热点追踪", "计算机视觉与多模态")),
    (r"Agent|Reinforcement|\bRL\b|Planning|Games|Decision|Control",
     ("AI热点追踪", "智能体与强化学习")),
    (r"Speech|Audio|ASR|Voice|TTS|Music", ("AI热点追踪", "语音技术")),
    (r"Safety|Alignment|Deceptive|Attack|Adversarial|Hackers|Jailbreak|Privacy"
     r"|Security|CVE|安全|对齐|攻击|漏洞",
     ("AI热点追踪", "AI 安全与伦理")),
    (r"Machine Learning|\bML\b|Graph|PAC|Bayesian|Causal|Statistic|Optimization"
     r"|Kernel|Tensor",
     ("AI热点追踪", "机器学习与算法")),
]

# 混装入「AI热点追踪」的嵌入式内容 → 移回嵌入式分类（放在 AI 规则之前匹配）
EMBEDDED_RECLASSIFY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (r"ESP-IDF 编程指南", None),  # 特殊：按标题关键词再分 API 参考/开发指南
    (r"#raspberrypi|#piday|Raspberry Pi", ("嵌入式开发", "树莓派")),
    (r"Hackaday", ("嵌入式开发", "技术社区文章")),
    (r"电子技术论坛", ("嵌入式开发", "电子电路")),
    (r"ESP32-CAM", ("嵌入式开发", "ESP32")),
]

IDF_API_KEYWORDS = re.compile(
    r"ADC|DAC|I2C|I2S|SPI|UART|LCD|LED|GPIO|Timer|MCPWM|PCNT|RMT|TWAI|CAN|"
    r"SDMMC|SDIO|以太网|PWM|脉冲|模数|数模|eFuse|RTC|USB|DMA|中断|调试|看门狗|"
    r"内存|flash|NVS|存储|随机数|SHA|AES|加密|OTA|bootloader|分区|控制台|日志|"
    r"wifi|Wi-Fi|蓝牙|BLE|HTTP|MQTT|TLS|智能配网|SmartConfig"
)
IDF_GUIDE_KEYWORDS = re.compile(r"安装|构建|卸载|工具链|环境|命令行|EIM|Eclipse|VS Code|工作流程|监控器")


def reclassify_category(title: str) -> Optional[tuple[str, ...]]:
    """按标题规则给出目标分类路径；返回 None 表示保持原分类。"""
    for pattern, path in EMBEDDED_RECLASSIFY_RULES:
        if not re.search(pattern, title):
            continue
        if path is not None:
            return path
        # ESP-IDF 编程指南：按关键词细分 API 参考 / 开发指南
        if IDF_API_KEYWORDS.search(title):
            return ("嵌入式开发", "ESP-IDF", "API 参考")
        if IDF_GUIDE_KEYWORDS.search(title):
            return ("嵌入式开发", "ESP-IDF", "开发指南")
        return ("嵌入式开发", "ESP-IDF", "API 参考")
    for pattern, path in RECLASSIFY_RULES:
        if re.search(pattern, title):
            return path
    return ("AI热点追踪", "AI 行业动态")


def reclassify_ai_docs(db: Session, ai_root_id: int) -> Counter:
    """把「AI热点追踪」根节点下混装的 338 篇存量文档按标题规则重归类。"""
    stats: Counter = Counter()
    docs = (
        db.query(Document)
        .filter(Document.category_id == ai_root_id)
        .all()
    )
    path_to_id: dict[tuple[str, ...], int] = {}
    for doc in docs:
        target = reclassify_category(doc.title or "")
        cat_id = path_to_id.get(target)
        if cat_id is None:
            cat_id = resolve_category_id(db, target)
            path_to_id[target] = cat_id
        if cat_id is None or cat_id == doc.category_id:
            stats["保持原分类"] += 1
            continue
        doc.category_id = cat_id
        stats[" -> ".join(target)] += 1
    db.commit()
    log.info("存量重归类完成（共 %d 篇，%d 篇未变）",
             len(docs), stats["保持原分类"])
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]):
        if k != "保持原分类":
            log.info("  %4d 篇 -> %s", v, k)
    return stats


# ==================== 批量导入主流程 ====================


def import_documents(zip_path: str, limit: Optional[int]) -> Counter:
    """解压 + 批量导入 md 文档到知识库。返回分类统计。"""
    log.info("扫描压缩包: %s", zip_path)
    items = scan_md_items(zip_path)
    log.info("共发现 %d 篇 md 文档", len(items))
    if limit:
        items = items[:limit]

    dest_root = Path(settings.UPLOAD_DIR) / IMPORT_SUBDIR
    log.info("解压 md 到 %s", dest_root)
    extracted = extract_md(zip_path, items, dest_root)

    idf_url_map = load_idf_url_map(dest_root)
    esp_url_map = load_espressif_url_map(dest_root)
    log.info("URL 映射：idf=%d 条，espressif=%d 条",
             len(idf_url_map), len(esp_url_map))

    # ---- 数据库准备：分类树 + 管理员 + 存量去重集合 ----
    db = SessionLocal()
    try:
        category_map = ensure_crawl_categories(db)
        admin_id = ensure_admin(db)
        log.info("分类树就绪（%d 个分类）", len(category_map))

        source_hashes = {
            r[0] for r in db.query(Document.source_hash).filter(
                Document.source_hash.isnot(None))
        }
        existing_titles = {
            (r[0] or "").strip().lower()
            for r in db.query(Document.title)
        }
        existing_hashes = _existing_content_hashes(db)
        log.info("存量去重基线：source_hash %d、标题 %d、内容哈希 %d",
                 len(source_hashes), len(existing_titles), len(existing_hashes))

        stats: Counter = Counter()
        cat_stats: Counter = Counter()
        path_id_cache: dict[tuple[str, ...], Optional[int]] = {}

        for idx, item in enumerate(items, 1):
            rel_path = item["rel_path"]
            source_hash = hashlib.sha256(
                f"zip_import:{rel_path}".encode("utf-8")).hexdigest()
            if source_hash in source_hashes:
                stats["skipped_hash"] += 1
                continue
            disk_path = extracted.get(rel_path)
            if disk_path is None or not disk_path.exists():
                stats["failed"] += 1
                continue
            try:
                content = disk_path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                stats["failed"] += 1
                continue
            title = extract_title(content, rel_path)
            if title.lower() in existing_titles:
                stats["skipped_title"] += 1
                continue
            body_hash = content_body_hash(content)
            if body_hash in existing_hashes:
                stats["skipped_content"] += 1
                continue

            cat_path = category_path_for(item)
            cat_id = path_id_cache.get(cat_path)
            if cat_id is None:
                cat_id = resolve_category_id(db, cat_path)
                path_id_cache[cat_path] = cat_id
            if cat_id is None:
                log.warning("分类解析失败 %s: %s", rel_path, cat_path)
                stats["failed"] += 1
                continue

            # source_url：论坛帖头 / idf 进度文件 / espressif 索引
            if item["site"] == "esp32_forum":
                source_url = extract_forum_url(content)
                pub_date = extract_forum_date(content)
            elif item["site"] == "esp_idf_zh_esp32":
                source_url = idf_url_map.get(rel_path.split("/", 1)[-1], "")
                pub_date = None
            else:
                source_url = esp_url_map.get(rel_path, "")
                pub_date = None

            tags = [item["site"], item["board"]] if item["board"] else [item["site"]]

            doc = Document(
                title=title,
                file_name=f"{IMPORT_SUBDIR}/{safe_disk_relpath(rel_path)}",
                file_path=str(disk_path),
                file_size=disk_path.stat().st_size,
                file_type="md",
                category_id=cat_id,
                tags=tags,
                security_level=1,
                status=0,  # 处理中
                created_by=admin_id,
                publish_date=pub_date or date.today(),
                source_url=source_url or None,
                source_hash=source_hash,
            )
            db.add(doc)
            db.flush()
            db.refresh(doc)
            db.commit()

            try:
                chunk_count, chunk_ids, chunk_records = process_document(
                    file_path=str(disk_path),
                    file_type="md",
                    document_id=doc.id,
                    title=title,
                    category_id=cat_id,
                    security_level=1,
                    source_url=source_url or "",
                    persist_index=False,  # 全量结束后统一持久化 BM25
                )
            except Exception as exc:  # noqa: BLE001 - 单文档失败不影响其他
                db.rollback()
                doc = db.query(Document).filter(Document.id == doc.id).first()
                if doc:
                    doc.status = 3
                    db.commit()
                log.warning("入库失败[%d/%d] %s: %s", idx, len(items),
                            title[:50], exc)
                stats["failed"] += 1
                continue

            # 写 DocChunk 行（与 _process_document_task 同范式）
            for i, chunk_id in enumerate(chunk_ids):
                chunk_info = chunk_records[i] if i < len(chunk_records) else {}
                db.add(DocChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    content=chunk_info.get("content", ""),
                    chapter=chunk_info.get("chapter", ""),
                    page_start=chunk_info.get("page", 1),
                    chroma_id=chunk_id,
                    token_count=chunk_info.get("token_count", 0),
                ))

            # 自动过审发布（公开技术资料，仅校内教学使用）
            doc.review_status = 2
            doc.reviewed_by = admin_id
            doc.reviewed_at = datetime.now()
            doc.review_comment = (
                f"压缩包批量导入：来源 {source_url or rel_path}；"
                f"仅校内教学使用，自动审核通过"
            )
            doc.status = 1
            db.commit()

            stats["synced"] += 1
            cat_stats[cat_path] += 1
            source_hashes.add(source_hash)
            # 注意：不把新标题加入 existing_titles——论坛中同名帖子是不同文档，
            # 标题去重只针对存量 KB 文档；内容哈希去重才在本次导入内生效
            existing_hashes.add(body_hash)

            if idx % 100 == 0:
                log.info("进度 %d/%d：成功 %d，跳过 %d，失败 %d",
                         idx, len(items), stats["synced"],
                         stats["skipped_hash"] + stats["skipped_title"]
                         + stats["skipped_content"], stats["failed"])
    finally:
        db.close()

    # 全部导入完成后统一持久化 BM25 索引一次
    save_bm25_index()
    log.info("BM25 索引已持久化")

    log.info("导入完成：成功 %d，hash跳过 %d，标题重复 %d，内容重复 %d，失败 %d",
             stats["synced"], stats["skipped_hash"], stats["skipped_title"],
             stats["skipped_content"], stats["failed"])
    log.info("分类分布：")
    for path, cnt in sorted(cat_stats.items(), key=lambda kv: -kv[1]):
        log.info("  %5d 篇 -> %s", cnt, " / ".join(path))
    return cat_stats


def _existing_content_hashes(db: Session) -> set[str]:
    """存量文档归一化正文哈希集合（文件缺失则跳过）。"""
    hashes: set[str] = set()
    for doc_id, file_path in db.query(Document.id, Document.file_path):
        if not file_path or not Path(file_path).exists():
            continue
        try:
            text = Path(file_path).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 - 非文本文件跳过
            continue
        hashes.add(content_body_hash(text))
    return hashes


# ==================== 入口 ====================


def main() -> None:
    parser = argparse.ArgumentParser(description="压缩包爬取文档批量导入知识库")
    parser.add_argument("--zip", default=DEFAULT_ZIP, help="压缩包路径")
    parser.add_argument("--limit", type=int, default=None, help="只导入前 N 篇（冒烟测试）")
    parser.add_argument("--dry-run", action="store_true", help="只统计分类分布，不写库")
    parser.add_argument("--only-reclassify", action="store_true",
                        help="只做存量 AI热点追踪 重归类")
    args = parser.parse_args()

    if args.only_reclassify:
        db = SessionLocal()
        try:
            ensure_crawl_categories(db)
            ai_root = (
                db.query(Category)
                .filter(Category.name == "AI热点追踪", Category.parent_id == 0)
                .first()
            )
            if ai_root is None:
                log.error("未找到 AI热点追踪 根分类")
                return
            reclassify_ai_docs(db, ai_root.id)
        finally:
            db.close()
        return

    if args.dry_run:
        items = scan_md_items(args.zip)
        dist: Counter = Counter()
        for item in items:
            dist[category_path_for(item)] += 1
        log.info("dry-run：共 %d 篇，分类分布：", len(items))
        for path, cnt in sorted(dist.items(), key=lambda kv: -kv[1]):
            log.info("  %5d 篇 -> %s", cnt, " / ".join(path))
        return

    import_documents(args.zip, args.limit)

    # 导入完成后顺带做存量重归类（幂等）
    db = SessionLocal()
    try:
        ai_root = (
            db.query(Category)
            .filter(Category.name == "AI热点追踪", Category.parent_id == 0)
            .first()
        )
        if ai_root is not None:
            reclassify_ai_docs(db, ai_root.id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
