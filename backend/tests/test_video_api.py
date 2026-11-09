# ============================================================
# 视频专区接口测试
# 直接调用路由函数（与项目现有测试保持一致的轻量风格）
# 覆盖：列表过滤 / 分类聚合 / 详情 404 / 重复 BV / 上下架 / 删除 / 权限
# ============================================================

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import deps
from app.api.v1 import videos as video_api
from app.core.exceptions import DuplicateException, NotFoundException
from app.models.video import Video
from app.schemas.video import VideoCreate, VideoUpdate


def _bvid() -> str:
    """生成唯一且符合 BV 正则的测试编号"""
    return "BV" + uuid.uuid4().hex[:10].upper()


def _list(db, user, **overrides):
    """调用学生端列表，显式填充全部 Query 参数（直接调用路由时默认值是 Query 对象）"""
    params = {
        "keyword": None, "category": None, "difficulty": None,
        "page": 1, "page_size": 12,
    }
    params.update(overrides)
    return video_api.list_videos(db=db, current_user=user, **params)


def _admin_list(db, user, **overrides):
    """调用管理端列表，显式填充全部 Query 参数"""
    params = {
        "keyword": None, "category": None, "status": None,
        "page": 1, "page_size": 20,
    }
    params.update(overrides)
    return video_api.admin_list_videos(db=db, current_user=user, **params)


def _create(db, user, **overrides):
    """通过路由函数新增一条视频，返回新建视频 id"""
    payload = {
        "title": "测试视频",
        "bvid": _bvid(),
        "cover_url": "https://example.com/cover.jpg",
        "up_name": "测试UP主",
        "duration": 600,
        "play_count": 100,
        "category": "ESP32",
        "difficulty": "入门",
        "description": "测试简介",
        "tags": ["ESP32", "入门"],
        "sort_order": 0,
        "status": 1,
    }
    payload.update(overrides)
    resp = video_api.create_video(
        VideoCreate(**payload), db=db, current_user=user,
    )
    assert resp.code == 0
    return resp.data["id"]


def test_list_only_published_and_filters(db, employee_user):
    """学生端列表只返回已上架，并支持分类/难度/关键词筛选"""
    esp32_basic = _create(db, employee_user, title="ESP32 入门教程", category="ESP32", difficulty="入门", sort_order=1)
    esp32_adv = _create(db, employee_user, title="ESP32 进阶实战", category="ESP32", difficulty="进阶", sort_order=2)
    arduino = _create(db, employee_user, title="Arduino 快速上手", category="Arduino", difficulty="入门", sort_order=3)
    _create(db, employee_user, title="已下架视频", category="ESP32", difficulty="入门", status=0, sort_order=4)

    resp = _list(db, employee_user)
    assert resp.data["total"] == 3
    assert {v["id"] for v in resp.data["items"]} == {esp32_basic, esp32_adv, arduino}
    # 排序号小的在前
    assert [v["id"] for v in resp.data["items"]] == [esp32_basic, esp32_adv, arduino]
    # 出参包含可跳转的 B 站地址
    assert resp.data["items"][0]["url"].startswith("https://www.bilibili.com/video/BV")

    resp = _list(db, employee_user, category="ESP32")
    assert resp.data["total"] == 2

    resp = _list(db, employee_user, difficulty="入门")
    assert resp.data["total"] == 2
    assert {v["id"] for v in resp.data["items"]} == {esp32_basic, arduino}

    resp = _list(db, employee_user, keyword="Arduino")
    assert resp.data["total"] == 1
    assert resp.data["items"][0]["id"] == arduino

    # 分页
    resp = _list(db, employee_user, page=2, page_size=2)
    assert resp.data["total"] == 3
    assert resp.data["total_pages"] == 2
    assert len(resp.data["items"]) == 1


def test_categories_aggregation(db, employee_user):
    """分类聚合只统计已上架视频"""
    _create(db, employee_user, category="ESP32")
    _create(db, employee_user, category="ESP32")
    _create(db, employee_user, category="Arduino")
    _create(db, employee_user, category="ESP32", status=0)

    resp = video_api.list_video_categories(db=db, current_user=employee_user)
    assert resp.code == 0
    counts = {item["name"]: item["count"] for item in resp.data}
    assert counts["ESP32"] == 2
    assert counts["Arduino"] == 1


def test_detail_and_not_found(db, employee_user):
    """详情返回上架视频；下架/不存在均抛 404 业务异常"""
    video_id = _create(db, employee_user, title="可播放的视频")

    resp = video_api.get_video(video_id, db=db, current_user=employee_user)
    assert resp.code == 0
    assert resp.data["id"] == video_id
    assert resp.data["bvid"] in resp.data["url"]

    down_id = _create(db, employee_user, title="已下架", status=0)
    with pytest.raises(NotFoundException) as exc:
        video_api.get_video(down_id, db=db, current_user=employee_user)
    assert exc.value.status_code == 404
    assert exc.value.code == 3001

    with pytest.raises(NotFoundException):
        video_api.get_video(999999, db=db, current_user=employee_user)


def test_create_duplicate_bvid(db, employee_user):
    """重复 BV 号必须抛 409，而不是返回成功"""
    bvid = _bvid()
    _create(db, employee_user, bvid=bvid, title="首个视频")

    with pytest.raises(DuplicateException) as exc:
        _create(db, employee_user, bvid=bvid, title="重复视频")
    assert exc.value.status_code == 409
    assert exc.value.code == 3002


def test_update_and_duplicate_bvid(db, employee_user):
    """编辑视频；改成已存在的 BV 号抛 409；编辑不存在的视频抛 404"""
    first_id = _create(db, employee_user, title="视频一")
    second_id = _create(db, employee_user, title="视频二")
    second_bvid = db.query(Video).filter(Video.id == second_id).first().bvid

    resp = video_api.update_video(
        first_id,
        VideoUpdate(title="视频一（已改名）", sort_order=10, difficulty="进阶"),
        db=db, current_user=employee_user,
    )
    assert resp.code == 0
    video = db.query(Video).filter(Video.id == first_id).first()
    assert video.title == "视频一（已改名）"
    assert video.sort_order == 10
    assert video.difficulty == "进阶"

    with pytest.raises(DuplicateException):
        video_api.update_video(
            first_id, VideoUpdate(bvid=second_bvid),
            db=db, current_user=employee_user,
        )

    with pytest.raises(NotFoundException):
        video_api.update_video(
            999999, VideoUpdate(title="不存在"),
            db=db, current_user=employee_user,
        )


def test_toggle_status_and_delete(db, employee_user):
    """上下架影响学生端可见性；删除后记录不存在；操作不存在记录抛 404"""
    video_id = _create(db, employee_user, title="待下架视频")

    resp = video_api.toggle_video_status(video_id, status=0, db=db, current_user=employee_user)
    assert resp.code == 0
    assert db.query(Video).filter(Video.id == video_id).first().status == 0

    list_resp = _list(db, employee_user)
    assert video_id not in {v["id"] for v in list_resp.data["items"]}

    resp = video_api.toggle_video_status(video_id, status=1, db=db, current_user=employee_user)
    assert resp.code == 0
    assert db.query(Video).filter(Video.id == video_id).first().status == 1

    with pytest.raises(NotFoundException):
        video_api.toggle_video_status(999999, status=0, db=db, current_user=employee_user)

    resp = video_api.delete_video(video_id, db=db, current_user=employee_user)
    assert resp.code == 0
    assert db.query(Video).filter(Video.id == video_id).first() is None

    with pytest.raises(NotFoundException):
        video_api.delete_video(999999, db=db, current_user=employee_user)


def test_admin_list_includes_offline_and_status_filter(db, employee_user):
    """管理端列表包含已下架视频，并支持状态筛选"""
    online_id = _create(db, employee_user, title="上架视频", status=1)
    offline_id = _create(db, employee_user, title="下架视频", status=0)

    resp = _admin_list(db, employee_user)
    assert resp.data["total"] == 2
    assert {v["id"] for v in resp.data["items"]} == {online_id, offline_id}

    resp = _admin_list(db, employee_user, status=0)
    assert resp.data["total"] == 1
    assert resp.data["items"][0]["id"] == offline_id


def test_admin_permission_checker():
    """require_knowledge_admin 拒绝学生/访客，放行知识库管理员"""
    student = SimpleNamespace(role=SimpleNamespace(code="student"))
    with pytest.raises(HTTPException) as exc:
        deps.require_knowledge_admin(current_user=student)
    assert exc.value.status_code == 403

    employee = SimpleNamespace(role=SimpleNamespace(code="employee"))
    with pytest.raises(HTTPException):
        deps.require_knowledge_admin(current_user=employee)

    admin = SimpleNamespace(role=SimpleNamespace(code="knowledge_admin"))
    assert deps.require_knowledge_admin(current_user=admin) is admin

    super_admin = SimpleNamespace(role=SimpleNamespace(code="super_admin"))
    assert deps.require_knowledge_admin(current_user=super_admin) is super_admin
