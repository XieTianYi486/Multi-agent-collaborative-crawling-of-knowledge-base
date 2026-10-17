# ============================================================
# 文档管理服务层
# 文档上传、解析、分块、检索、版本管理
# ============================================================

import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional, BinaryIO

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.exceptions import (
    NotFoundException,
    DocumentProcessException,
    ValidationException,
)
from app.models.document import Document, DocumentVersion, DocChunk, Category
from app.schemas.document import DocumentUpdate
from app.tasks.document_tasks import process_document_async, reindex_document_async
from app.rag.ingestion import remove_document_from_index
from app.db.cache import cache


class DocumentService:
    """文档管理业务逻辑"""

    # ==================== 缓存失效 ====================

    @staticmethod
    def _invalidate_qa_cache() -> None:
        """知识库内容变更后，清除全部单轮问答缓存，避免命中过期答案"""
        cache.clear_by_prefix("qa")

    # 文件类型映射
    SUPPORTED_TYPES = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".md": "md",
        ".markdown": "md",
        ".txt": "txt",
    }

    @classmethod
    def get_file_type(cls, filename: str) -> str:
        """根据文件扩展名判断文件类型"""
        ext = Path(filename).suffix.lower()
        if ext not in cls.SUPPORTED_TYPES:
            raise ValidationException(
                f"不支持的文件格式：{ext}。支持：{', '.join(cls.SUPPORTED_TYPES.keys())}"
            )
        return cls.SUPPORTED_TYPES[ext]

    @staticmethod
    def resolve_document_path(doc: Document) -> Optional[str]:
        """解析文档文件的真实磁盘路径。

        历史文档入库时可能保存了包含旧目录名的绝对路径（项目文件夹改名后失效），
        此时回退到 UPLOAD_DIR 下按文件名查找，保证内容读取不受目录改名影响。
        """
        stored = doc.file_path or ""
        if stored and os.path.exists(stored):
            return stored
        fallback = Path(settings.UPLOAD_DIR) / Path(stored).name
        return str(fallback) if fallback.exists() else None

    @classmethod
    def create_document(
        cls,
        db: Session,
        file: BinaryIO,
        filename: str,
        title: Optional[str] = None,
        category_id: Optional[int] = None,
        tags: Optional[list] = None,
        user_id: Optional[int] = None,
    ) -> Document:
        """上传并创建文档记录"""
        file_type = cls.get_file_type(filename)

        # 生成唯一存放文件名
        stored_name = f"{uuid.uuid4().hex}_{filename}"
        upload_path = Path(settings.UPLOAD_DIR) / stored_name

        # 写入文件
        content = file.read()
        file_size = len(content)
        upload_path.write_bytes(content)

        # 创建数据库记录
        doc = Document(
            title=title or Path(filename).stem,
            file_name=filename,
            file_path=str(upload_path),
            file_size=file_size,
            file_type=file_type,
            category_id=category_id,
            tags=tags or [],
            status=0,  # 处理中
            created_by=user_id,
            publish_date=date.today(),
        )
        db.add(doc)
        db.flush()
        db.refresh(doc)
        cls._invalidate_qa_cache()
        return doc

    @classmethod
    def get_documents(
        cls,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        category_id: Optional[int] = None,
        file_type: Optional[str] = None,
        status: Optional[int] = None,
        security_level: Optional[int] = None,
        review_status: Optional[int] = None,
        published_only: bool = False,
    ) -> tuple[list[Document], int]:
        """文档列表（分页、筛选）"""
        query = db.query(Document)

        if keyword:
            query = query.filter(
                (Document.title.contains(keyword)) |
                (Document.file_name.contains(keyword))
            )
        if category_id is not None:
            query = query.filter(Document.category_id == category_id)
        if file_type:
            query = query.filter(Document.file_type == file_type)
        if status is not None:
            query = query.filter(Document.status == status)
        if security_level is not None:
            query = query.filter(Document.security_level == security_level)
        if review_status is not None:
            query = query.filter(Document.review_status == review_status)
        # 普通可见文档：已发布 + 已通过审核
        if published_only:
            query = query.filter(
                Document.status == 1,
                Document.review_status == 2,
            )

        total = query.count()
        items = query.order_by(Document.created_at.desc()) \
            .offset((page - 1) * page_size) \
            .limit(page_size).all()

        return items, total

    @classmethod
    def review_document(
        cls, db: Session, doc_id: int, action: str,
        reviewer_id: Optional[int] = None, comment: Optional[str] = None,
    ) -> Document:
        """
        文档审核流转。

        支持的 action:
          - approve : 通过（review_status -> 2 已通过，可被检索/员工可见）
          - reject  : 驳回（review_status -> 3 已驳回，记录审核意见）
          - submit  : 提交审核（草稿/驳回 -> 待审核 1）
          - recall  : 撤回（待审核 -> 草稿 0）
        """
        from datetime import datetime, timezone
        doc = cls.get_document(db, doc_id)
        if action == "approve":
            doc.review_status = 2
            doc.status = 1
            doc.review_comment = comment
        elif action == "reject":
            doc.review_status = 3
            doc.review_comment = comment
        elif action == "submit":
            # 草稿(0) 或 已驳回(3) 均可重新提交审核
            if doc.review_status not in (0, 3):
                raise ValidationException("仅草稿或被驳回的文档可提交审核")
            doc.review_status = 1
            doc.review_comment = None
        elif action == "recall":
            # 待审核(1) 可撤回为草稿
            if doc.review_status != 1:
                raise ValidationException("仅待审核的文档可撤回")
            doc.review_status = 0
        else:
            raise ValidationException("无效的审核动作")
        doc.reviewed_by = reviewer_id
        doc.reviewed_at = datetime.now(timezone.utc)
        db.flush()
        db.refresh(doc)
        cls._invalidate_qa_cache()
        return doc

    @classmethod
    def get_document(cls, db: Session, doc_id: int) -> Document:
        """获取单个文档"""
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise NotFoundException("文档不存在")
        return doc

    @classmethod
    def update_document(cls, db: Session, doc_id: int, data: DocumentUpdate) -> Document:
        """更新文档元数据"""
        doc = cls.get_document(db, doc_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(doc, key, value)

        db.flush()
        db.refresh(doc)
        cls._invalidate_qa_cache()
        return doc

    @classmethod
    def delete_document(cls, db: Session, doc_id: int) -> None:
        """删除文档（同时清理文件和分块数据）"""
        doc = cls.get_document(db, doc_id)

        # 从向量库和 BM25 索引中移除
        try:
            remove_document_from_index(doc.id)
        except Exception:
            pass

        # 删除物理文件
        try:
            os.remove(doc.file_path)
        except FileNotFoundError:
            pass

        # 删除数据库记录（CASCADE 会删除 chunks 和 versions）
        db.delete(doc)
        db.flush()
        cls._invalidate_qa_cache()

    @classmethod
    def reindex_document(cls, doc_id: int) -> None:
        """重新索引文档（异步）"""
        cls._invalidate_qa_cache()
        reindex_document_async(doc_id)

    @classmethod
    def upload_new_version(
        cls,
        db: Session,
        doc_id: int,
        file: BinaryIO,
        filename: str,
        changelog: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Document:
        """
        上传文档新版本

        流程：
        1. 归档当前版本到 DocumentVersion
        2. 删除旧索引
        3. 保存新文件
        4. 更新文档记录
        5. 异步重新索引
        """
        doc = cls.get_document(db, doc_id)

        file_type = cls.get_file_type(filename)

        # 1. 归档旧版本
        version_record = DocumentVersion(
            document_id=doc.id,
            version=doc.version,
            file_path=doc.file_path,
            file_size=doc.file_size,
            changelog=changelog,
        )
        db.add(version_record)

        # 2. 删除旧索引
        try:
            remove_document_from_index(doc.id)
        except Exception:
            pass

        # 3. 保存新文件
        stored_name = f"{uuid.uuid4().hex}_{filename}"
        upload_path = Path(settings.UPLOAD_DIR) / stored_name

        content = file.read()
        file_size = len(content)
        upload_path.write_bytes(content)

        # 4. 更新文档记录
        # 版本号递增：1.0 → 1.1, 2.0 → 2.1
        old_version = doc.version
        parts = old_version.split(".")
        if len(parts) == 2 and parts[1].isdigit():
            new_version = f"{parts[0]}.{int(parts[1]) + 1}"
        else:
            new_version = f"{old_version}.1"

        doc.file_name = filename
        doc.file_path = str(upload_path)
        doc.file_size = file_size
        doc.file_type = file_type
        doc.version = new_version
        doc.status = 0  # 处理中
        db.flush()
        db.refresh(doc)
        cls._invalidate_qa_cache()

        # 5. 异步重新索引（在 db 事务提交后启动，避免后台线程访问未提交数据）
        return doc

    @classmethod
    def start_reindex_after_commit(cls, doc_id: int) -> None:
        """在事务提交后启动重新索引"""
        reindex_document_async(doc_id)

    @classmethod
    def get_stats(cls, db: Session) -> dict:
        """文档统计"""
        total = db.query(Document).count()
        total_chunks = db.query(DocChunk).count()
        total_size = db.query(func.sum(Document.file_size)).scalar() or 0

        # 按状态统计
        by_status = {}
        for row in db.query(Document.status, func.count(Document.id)).group_by(Document.status).all():
            by_status[str(row[0])] = row[1]

        # 按文件类型统计
        by_file_type = {}
        for row in db.query(Document.file_type, func.count(Document.id)).group_by(Document.file_type).all():
            by_file_type[row[0]] = row[1]

        # 按分类统计
        by_category = {}
        for row in db.query(Category.name, func.count(Document.id)) \
                .join(Document, Document.category_id == Category.id, isouter=True) \
                .group_by(Category.name).all():
            by_category[row[0] or "未分类"] = row[1]

        return {
            "total_documents": total,
            "total_chunks": total_chunks,
            "total_size_bytes": total_size,
            "by_status": by_status,
            "by_file_type": by_file_type,
            "by_category": by_category,
        }
