#!/usr/bin/env python3
# ============================================================
# 人工智能学院教学知识库 - 学生名单同步（幂等，可重复执行）
# 读取 deploy/students.json，创建缺失的班级部门与学生账号（默认密码 123456）
# 用法：KB_APP_DIR=/opt/kb /opt/kb/backend/.venv/bin/python /opt/kb/deploy/sync_students.py
# ============================================================
import json
import os
import sys
from pathlib import Path

APP_DIR = Path(os.environ.get("KB_APP_DIR", "/opt/kb")).resolve()
BACKEND_DIR = APP_DIR / "backend"
DATA_FILE = APP_DIR / "deploy" / "students.json"

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.core.security import hash_password  # noqa: E402
from app.db.sqlite import SessionLocal  # noqa: E402
from app.models.user import Department, User  # noqa: E402

DEFAULT_PASSWORD = "123456"
STUDENT_ROLE_ID = 6


def main() -> int:
    rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print(f"[students] 名单 {len(rows)} 条，默认密码 {DEFAULT_PASSWORD}")

    db = SessionLocal()
    try:
        existing_depts = {d.name for d in db.query(Department).all()}
        dept_names = []
        for row in rows:
            if row["dept"] not in dept_names:
                dept_names.append(row["dept"])

        created_depts = 0
        sort_order = 10
        for name in dept_names:
            if name in existing_depts:
                continue
            major = next(r["major"] for r in rows if r["dept"] == name)
            db.add(Department(
                name=name, parent_id=0, dept_type="class",
                description=major, sort_order=sort_order,
            ))
            existing_depts.add(name)
            created_depts += 1
            sort_order += 1
        db.commit()
        print(f"[students] 新建班级部门 {created_depts} 个，现有 {len(existing_depts)} 个")

        existing_users = {u for (u,) in db.query(User.username).all()}
        created = skipped = 0
        for row in rows:
            if row["sid"] in existing_users:
                skipped += 1
                continue
            db.add(User(
                username=row["sid"],
                password_hash=hash_password(DEFAULT_PASSWORD),
                real_name=row["name"],
                department=row["dept"],
                role_id=STUDENT_ROLE_ID,
                status=1,
                gender=None,
            ))
            existing_users.add(row["sid"])
            created += 1
            if created % 50 == 0:
                db.commit()
                print(f"[students] 已创建 {created} 个账号 ...", flush=True)
        db.commit()
        print(f"[students] 新建账号 {created} 个，已存在跳过 {skipped} 个")
        print(f"[students] 用户总数 {db.query(User).count()}，"
              f"学生账号 {db.query(User).filter(User.role_id == STUDENT_ROLE_ID).count()}，"
              f"班级部门 {db.query(Department).filter(Department.dept_type == 'class').count()}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
