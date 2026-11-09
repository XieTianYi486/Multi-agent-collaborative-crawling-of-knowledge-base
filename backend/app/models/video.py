# ============================================================
# 视频专区模型
# 仅保存 B 站视频元数据，不转存视频文件
# 播放时通过 bvid 嵌入 B 站官方播放器
# ============================================================

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, JSON, DateTime, Index,
)

from app.db.sqlite import Base


class Video(Base):
    """精选视频表（B 站入门经典）"""

    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False, comment="视频标题")
    bvid = Column(
        String(32), nullable=False, unique=True,
        comment="B 站 BV 号，用于构建播放器地址",
    )
    cover_url = Column(String(600), nullable=True, comment="封面图地址")
    up_name = Column(String(128), nullable=True, comment="UP 主名称")
    duration = Column(Integer, default=0, comment="视频时长（秒）")
    play_count = Column(Integer, default=0, comment="B 站播放量（用于展示热度）")
    category = Column(
        String(64), nullable=False, default="嵌入式开发",
        comment="方向分类：ESP32 / ESP-IDF / Arduino / FreeRTOS 等",
    )
    difficulty = Column(
        String(32), nullable=False, default="入门", comment="难度：入门 / 进阶",
    )
    description = Column(Text, nullable=True, comment="视频简介 / 推荐理由")
    tags = Column(JSON, nullable=True, comment="标签列表（JSON 数组）")
    sort_order = Column(Integer, default=0, nullable=False, comment="排序号，越小越靠前")
    status = Column(
        Integer, default=1, nullable=False, comment="状态：1=已上架, 0=已下架",
    )
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间",
    )

    __table_args__ = (
        Index("ix_videos_category", "category"),
        Index("ix_videos_status_sort", "status", "sort_order"),
    )

    def __repr__(self):
        return f"<Video(id={self.id}, bvid='{self.bvid}', title='{self.title}')>"
