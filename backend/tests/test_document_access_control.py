# ============================================================
# 文档访问控制测试：密级上限、审核状态、收藏夹 ID 过滤
# ============================================================

import uuid

import pytest

from app.core.exceptions import PermissionDeniedException
from app.models.document import Document
from app.services.document_service import DocumentService


@pytest.fixture(autouse=True)
def _cleanup_created_docs(db):
    """清理本文件提交的文档，避免污染依赖全量计数的其他用例"""
    yield
    db.query(Document).filter(Document.title.like("权限测试-%")).delete(
        synchronize_session=False
    )
    db.commit()


def _make_doc(db, security_level=1, status=1, review_status=2):
    title = f"权限测试-{uuid.uuid4().hex[:6]}"
    doc = Document(
        title=title,
        file_name=f"{title}.md",
        file_path=f"/tmp/{title}.md",
        file_type="md",
        security_level=security_level,
        status=status,
        review_status=review_status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_employee_cannot_read_internal_doc(db):
    doc = _make_doc(db, security_level=2)
    with pytest.raises(PermissionDeniedException):
        DocumentService.ensure_document_visible(doc, "employee")


def test_employee_cannot_read_unreviewed_doc(db):
    doc = _make_doc(db, security_level=1, review_status=1)
    with pytest.raises(PermissionDeniedException):
        DocumentService.ensure_document_visible(doc, "employee")


def test_admin_can_read_any_doc(db):
    doc = _make_doc(db, security_level=4, review_status=1)
    # 不抛异常即通过
    DocumentService.ensure_document_visible(doc, "knowledge_admin")
    DocumentService.ensure_document_visible(doc, "super_admin")


def test_dept_admin_level_cap(db):
    allowed = _make_doc(db, security_level=3)
    denied = _make_doc(db, security_level=4)

    DocumentService.ensure_document_visible(allowed, "dept_admin")
    with pytest.raises(PermissionDeniedException):
        DocumentService.ensure_document_visible(denied, "dept_admin")


def test_list_filters_by_security_level_and_review(db):
    visible = _make_doc(db, security_level=1)
    internal = _make_doc(db, security_level=2)
    unreviewed = _make_doc(db, security_level=1, review_status=0)

    items, _ = DocumentService.get_documents(
        db, max_security_level=1, published_only=True,
    )
    ids = [item.id for item in items]

    assert visible.id in ids
    assert internal.id not in ids
    assert unreviewed.id not in ids


def test_list_filters_by_ids(db):
    keep = _make_doc(db)
    other = _make_doc(db)

    items, total = DocumentService.get_documents(db, document_ids=[keep.id])

    assert total == 1
    assert [item.id for item in items] == [keep.id]
    assert other.id not in [item.id for item in items]
