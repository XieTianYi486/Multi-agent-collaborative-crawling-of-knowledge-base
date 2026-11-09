# ============================================================
# 教学关系 API：老师 ↔ 班级 ↔ 学生
#
# 权限设计：
# - 授课关系由超级管理员分配（新增/删除）
# - 教师只能查看自己任课班级的学生
# - 管理员可查看任意班级（便于运营核查）
# ============================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_active_user, require_super_admin
from app.db.sqlite import get_db
from app.models.chat import ChatLog
from app.models.collection import CollectionRequest
from app.models.document import Document
from app.models.teaching import TeachingAssignment
from app.models.user import Department, Role, User
from app.schemas.common import APIResponse
from app.schemas.teaching import AssignmentCreate

router = APIRouter(prefix="/teaching", tags=["教学关系"])

ADMIN_ROLES = {"super_admin", "knowledge_admin"}
TEACHER_ROLES = {"teacher"}


def _assignment_dict(a: TeachingAssignment, db: Session, cache: dict) -> dict:
    """序列化授课关系（带教师姓名与班级名，按需缓存避免重复查询）"""
    if a.teacher_id not in cache:
        teacher = db.query(User).filter(User.id == a.teacher_id).first()
        cache[a.teacher_id] = teacher
    teacher = cache[a.teacher_id]
    return {
        "id": a.id,
        "teacher_id": a.teacher_id,
        "teacher_name": (teacher.real_name or teacher.username) if teacher else None,
        "teacher_username": teacher.username if teacher else None,
        "teacher_department": teacher.department if teacher else None,
        "class_id": a.class_id,
        "subject": a.subject,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ==================== 管理员：分配授课关系 ====================

@router.get("/teachers", response_model=APIResponse, summary="教师列表（分配用）")
def list_teachers(
    keyword: Optional[str] = Query(default=None, description="按姓名/账号搜索"),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    query = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(Role.code == "teacher", User.status == 1)
    )
    if keyword:
        query = query.filter(
            (User.real_name.contains(keyword)) | (User.username.contains(keyword))
        )
    users = query.order_by(User.id.desc()).limit(200).all()
    return APIResponse(
        code=0, message="success",
        data=[
            {
                "id": u.id,
                "username": u.username,
                "real_name": u.real_name,
                "department": u.department,
            }
            for u in users
        ],
    )


@router.get("/assignments", response_model=APIResponse, summary="授课关系列表")
def list_assignments(
    class_id: Optional[int] = Query(default=None),
    teacher_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    query = db.query(TeachingAssignment)
    if class_id is not None:
        query = query.filter(TeachingAssignment.class_id == class_id)
    if teacher_id is not None:
        query = query.filter(TeachingAssignment.teacher_id == teacher_id)
    rows = query.order_by(TeachingAssignment.class_id, TeachingAssignment.id).all()
    cache: dict = {}
    return APIResponse(
        code=0, message="success",
        data=[_assignment_dict(a, db, cache) for a in rows],
    )


@router.post("/assignments", response_model=APIResponse, summary="分配任课老师")
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    teacher = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.id == payload.teacher_id)
        .first()
    )
    if teacher is None:
        return APIResponse(code=3001, message="教师不存在")
    if teacher.role is None or teacher.role.code != "teacher":
        return APIResponse(code=3002, message="该用户不是教师角色")
    if teacher.status != 1:
        return APIResponse(code=3003, message="该教师账号已被禁用")

    dept = db.query(Department).filter(Department.id == payload.class_id).first()
    if dept is None:
        return APIResponse(code=3004, message="班级不存在")
    if dept.dept_type != "class":
        return APIResponse(code=3005, message="只能给「班级」类型分配任课老师")

    exists = (
        db.query(TeachingAssignment)
        .filter(
            TeachingAssignment.teacher_id == payload.teacher_id,
            TeachingAssignment.class_id == payload.class_id,
        )
        .first()
    )
    if exists is not None:
        return APIResponse(code=3006, message="该老师已分配到此班级")

    assignment = TeachingAssignment(
        teacher_id=payload.teacher_id,
        class_id=payload.class_id,
        subject=payload.subject or None,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return APIResponse(
        code=0, message="分配成功",
        data=_assignment_dict(assignment, db, {}),
    )


@router.delete("/assignments/{assignment_id}", response_model=APIResponse, summary="取消授课关系")
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    assignment = (
        db.query(TeachingAssignment)
        .filter(TeachingAssignment.id == assignment_id)
        .first()
    )
    if assignment is None:
        return APIResponse(code=3001, message="授课关系不存在")
    db.delete(assignment)
    db.commit()
    return APIResponse(code=0, message="已取消")


# ==================== 教师：我的班级与学生 ====================

def _require_teacher_or_admin(current_user: User) -> str:
    role_code = current_user.role.code if current_user.role else ""
    if role_code not in ADMIN_ROLES and role_code not in TEACHER_ROLES:
        raise HTTPException(status_code=403, detail="仅教师或管理员可查看班级学生")
    return role_code


@router.get("/my-classes", response_model=APIResponse, summary="我的班级")
def list_my_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    role_code = _require_teacher_or_admin(current_user)
    query = db.query(TeachingAssignment)
    if role_code in TEACHER_ROLES:
        query = query.filter(TeachingAssignment.teacher_id == current_user.id)
    assignments = query.order_by(TeachingAssignment.class_id).all()

    dept_ids = {a.class_id for a in assignments}
    depts = (
        db.query(Department).filter(Department.id.in_(dept_ids)).all()
        if dept_ids else []
    )
    dept_map = {d.id: d for d in depts}

    student_counts = {}
    if depts:
        rows = (
            db.query(User.department, func.count(User.id))
            .join(Role, User.role_id == Role.id)
            .filter(
                Role.code == "student",
                User.status == 1,
                User.department.in_([d.name for d in depts]),
            )
            .group_by(User.department)
            .all()
        )
        student_counts = {name: count for name, count in rows}

    data = []
    for a in assignments:
        dept = dept_map.get(a.class_id)
        if dept is None:
            continue
        data.append({
            "class_id": a.class_id,
            "class_name": dept.name,
            "subject": a.subject,
            "student_count": student_counts.get(dept.name, 0),
        })
    return APIResponse(code=0, message="success", data=data)


@router.get(
    "/my-classes/{class_id}/students",
    response_model=APIResponse,
    summary="班级学生列表（含学习数据）",
)
def list_class_students(
    class_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: Optional[str] = Query(default=None, description="按姓名/账号搜索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    role_code = _require_teacher_or_admin(current_user)

    dept = db.query(Department).filter(Department.id == class_id).first()
    if dept is None or dept.dept_type != "class":
        return APIResponse(code=3004, message="班级不存在")

    # 教师只能看自己任课的班级
    if role_code in TEACHER_ROLES:
        owned = (
            db.query(TeachingAssignment)
            .filter(
                TeachingAssignment.teacher_id == current_user.id,
                TeachingAssignment.class_id == class_id,
            )
            .first()
        )
        if owned is None:
            raise HTTPException(status_code=403, detail="你没有任教该班级，无法查看学生信息")

    query = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .options(joinedload(User.role))
        .filter(
            Role.code == "student",
            User.status == 1,
            User.department == dept.name,
        )
    )
    if keyword:
        query = query.filter(
            (User.real_name.contains(keyword)) | (User.username.contains(keyword))
        )
    total = query.count()
    students = (
        query.order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    ids = [s.id for s in students]
    chat_counts, last_ask, doc_counts, collection_counts = {}, {}, {}, {}
    if ids:
        chat_counts = dict(
            db.query(ChatLog.user_id, func.count(ChatLog.id))
            .filter(ChatLog.user_id.in_(ids))
            .group_by(ChatLog.user_id)
            .all()
        )
        last_ask = dict(
            db.query(ChatLog.user_id, func.max(ChatLog.created_at))
            .filter(ChatLog.user_id.in_(ids))
            .group_by(ChatLog.user_id)
            .all()
        )
        doc_counts = dict(
            db.query(Document.created_by, func.count(Document.id))
            .filter(Document.created_by.in_(ids))
            .group_by(Document.created_by)
            .all()
        )
        collection_counts = dict(
            db.query(CollectionRequest.created_by, func.count(CollectionRequest.id))
            .filter(CollectionRequest.created_by.in_(ids))
            .group_by(CollectionRequest.created_by)
            .all()
        )

    rows = []
    for s in students:
        rows.append({
            "id": s.id,
            "username": s.username,
            "real_name": s.real_name,
            "gender": s.gender,
            "department": s.department,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "chat_count": chat_counts.get(s.id, 0),
            "last_ask_at": (
                last_ask.get(s.id).isoformat()
                if last_ask.get(s.id) else None
            ),
            "doc_count": doc_counts.get(s.id, 0),
            "collection_count": collection_counts.get(s.id, 0),
        })

    return APIResponse(
        code=0, message="success",
        data={
            "class_id": dept.id,
            "class_name": dept.name,
            "total": total,
            "items": rows,
        },
    )
