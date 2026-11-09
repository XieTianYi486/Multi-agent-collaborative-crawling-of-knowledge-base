# ============================================================
# 文档全文检索单元测试：标题 / 文件名 / 分块正文本路匹配 + 命中片段
# ============================================================

from app.models.document import Document, DocChunk
from app.services.document_service import DocumentService


def _make_doc(db, title, content=""):
    doc = Document(
        title=title,
        file_name=f"{title}.md",
        file_path=f"/tmp/{title}.md",
        file_type="md",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    if content:
        db.add(DocChunk(document_id=doc.id, chunk_index=0, content=content))
        db.commit()
    return doc


def test_keyword_matches_chunk_content(db):
    """关键词只在正文出现时，也应检索到该文档"""
    doc = _make_doc(
        db,
        "ESP32 启动排查记录",
        content="设备上电后无输出，重点检查供电电压与串口日志。",
    )

    items, total = DocumentService.get_documents(db, keyword="供电电压")

    assert total >= 1
    assert doc.id in [item.id for item in items]


def test_match_snippet_contains_keyword(db):
    """命中正文时返回关键词附近的片段，便于列表预览"""
    doc = _make_doc(
        db,
        "树莓派供电说明",
        content="树莓派供电不足时会出现彩虹屏，建议使用 5V 3A 电源适配器。",
    )

    snippets = DocumentService.get_match_snippets(db, [doc.id], "彩虹屏")

    assert doc.id in snippets
    assert "彩虹屏" in snippets[doc.id]
