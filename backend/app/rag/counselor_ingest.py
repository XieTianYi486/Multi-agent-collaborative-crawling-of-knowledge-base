# ============================================================
# 导员知识库导入
# 将校规/学术规范类 Markdown 文档按"条"切分，写入 counselor_kb_chunks，
# 并计算条款向量（JSON 落库），供导员检索器在内存中构建独立索引。
# 全程不写入教学知识库的任何表或索引。
# ============================================================

import glob
import logging
import os
import re
from typing import Dict, List, Optional

from app.core.config import settings
from app.db.sqlite import SessionLocal
from app.models.counselor import CounselorKbChunk

logger = logging.getLogger(__name__)

# 行首条文标记，允许"第九条 国家奖学金评定条件"这种带小标题的内联写法
ARTICLE_RE = re.compile(r"^第([一二三四五六七八九十百]+)条(?:\s+(.+))?$")
CHAPTER_RE = re.compile(r"^第([一二三四五六七八九十]+)章(.*)$")


def _clean_title(raw: str) -> str:
    title = raw.lstrip("#").strip()
    return title.replace("_修订", "").strip()


def parse_md(path: str) -> List[Dict]:
    """
    解析单个校规 Markdown 文档，按"条"切分为条款列表。

    返回: [{source_title, source_url, chapter, article_no, content, search_text}, ...]
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    source_title = os.path.splitext(os.path.basename(path))[0]
    source_url = ""
    for line in lines:
        s = line.strip()
        if s.startswith("# "):
            source_title = _clean_title(s)
        elif s.startswith("> 来源"):
            source_url = s.split("来源", 1)[1].lstrip(":：").strip()
        if source_title and source_url:
            break

    articles: List[Dict] = []
    chapter = ""
    article_no: Optional[str] = None
    buffer: List[str] = []

    def flush():
        nonlocal article_no, buffer
        if article_no and buffer:
            content = "\n".join(buffer).strip()
            if content:
                articles.append({
                    "source_title": source_title,
                    "source_url": source_url,
                    "chapter": chapter,
                    "article_no": article_no,
                    "content": content,
                    "search_text": (
                        f"《{source_title}》{chapter} {article_no}\n{content}"
                    ),
                })
        article_no = None
        buffer = []

    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.startswith("#") or s.startswith(">") or s == "---":
            i += 1
            continue

        m_ch = CHAPTER_RE.match(s)
        if m_ch:
            flush()
            num, rest = m_ch.group(1), m_ch.group(2).strip()
            if not rest:  # 章节名在下一行
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    nxt = lines[j].strip()
                    if not ARTICLE_RE.match(nxt) and not CHAPTER_RE.match(nxt):
                        rest = nxt
                        i = j  # 消费该标题行
            chapter = f"第{num}章" + (f" {rest}" if rest else "")
            i += 1
            continue

        m_at = ARTICLE_RE.match(s)
        if m_at:
            flush()
            article_no = f"第{m_at.group(1)}条"
            title_tail = (m_at.group(2) or "").strip()
            if title_tail:
                buffer.append(title_tail)
            i += 1
            continue

        if article_no is not None:
            buffer.append(s)
        i += 1

    flush()
    return articles


def ingest_counselor_kb(
    paths: Optional[List[str]] = None,
    rebuild: bool = True,
    with_embeddings: bool = True,
) -> Dict:
    """
    导入导员知识库。

    参数:
        paths: 源文件路径列表（默认读取 settings.COUNSELOR_KB_DIR 下所有 .md）
        rebuild: 是否清空既有条款后重建（默认 True）
        with_embeddings: 是否计算条款向量（False 时退化为纯 BM25 检索）

    返回:
        {"files": int, "articles": int, "embedded": int}
    """
    if paths is None:
        pattern = os.path.join(settings.COUNSELOR_KB_DIR, "*.md")
        paths = sorted(glob.glob(pattern))

    articles: List[Dict] = []
    for p in paths:
        parsed = parse_md(p)
        logger.info("解析 %s：%d 条", os.path.basename(p), len(parsed))
        articles.extend(parsed)

    if not articles:
        return {"files": 0, "articles": 0, "embedded": 0}

    # 计算向量（失败则整体退化为纯 BM25）
    embeddings: List[Optional[List[float]]] = [None] * len(articles)
    if with_embeddings:
        try:
            from app.rag.embeddings.dashscope_embeddings import get_embeddings
            embeddings = get_embeddings().embed_documents(
                [a["search_text"] for a in articles]
            )
        except Exception as e:
            logger.warning("导员知识库向量化失败，退化为纯 BM25 检索：%s", e)
            embeddings = [None] * len(articles)

    db = SessionLocal()
    try:
        if rebuild:
            db.query(CounselorKbChunk).delete()
        for art, emb in zip(articles, embeddings):
            db.add(CounselorKbChunk(
                source_title=art["source_title"],
                article_no=art["article_no"],
                chapter=art["chapter"],
                content=art["content"],
                source_url=art["source_url"],
                embedding=list(emb) if emb else None,
            ))
        db.commit()
    finally:
        db.close()

    # 让检索器重新加载（若已初始化）
    try:
        from app.rag.retrievers.counselor_retriever import get_counselor_retriever
        get_counselor_retriever().reload()
    except Exception:
        pass

    embedded = sum(1 for e in embeddings if e)
    return {"files": len(paths), "articles": len(articles), "embedded": embedded}
