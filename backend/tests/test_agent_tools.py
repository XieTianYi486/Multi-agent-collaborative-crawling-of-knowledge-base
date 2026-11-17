# ============================================================
# AI 助手工具层测试
# 覆盖：角色可见工具、参数校验、越权拦截、确认令牌一次性消费、意图门控
# ============================================================

import uuid

import pytest

from app.agent.registry import (
    ToolArgumentError, ToolContext, get_tool_registry,
)
from app.agent.routing import should_use_tools
from app.models.chat import ChatLog
from app.models.teaching import TeachingAssignment
from app.models.user import Department, User


class TestToolRegistry:
    def test_role_filtering(self):
        """学生看不到教师/管理员工具，教师看不到管理员工具"""
        registry = get_tool_registry()

        student = {t.name for t in registry.for_role("student")}
        teacher = {t.name for t in registry.for_role("teacher")}
        admin = {t.name for t in registry.for_role("super_admin")}

        assert "search_knowledge" in student
        assert "submit_collection_request" in student
        assert "class_students" not in student
        assert "get_admin_overview" not in student
        assert "class_question_hotspots" not in student
        assert "list_pending_documents" not in student

        assert "class_students" in teacher
        assert "list_my_classes" in teacher
        assert "class_question_hotspots" in teacher
        assert "student_learning_profile" in teacher
        assert "get_admin_overview" not in teacher
        assert "list_pending_work" not in teacher

        assert "get_admin_overview" in admin
        assert "class_students" in admin
        assert "list_pending_documents" in admin
        assert "knowledge_gap_report" in admin
        assert "platform_usage_stats" in admin
        assert "account_overview" in admin
        assert "audit_summary" in admin

    def test_openai_schema_shape(self):
        registry = get_tool_registry()
        tools = registry.openai_tools("student")
        assert tools
        for tool in tools:
            assert tool["type"] == "function"
            assert tool["function"]["name"]
            assert tool["function"]["parameters"]["type"] == "object"

    def test_validate_args_coerces_types(self):
        registry = get_tool_registry()
        spec = registry.get("get_document_detail")

        cleaned = registry.validate_args(spec, {"document_id": "12"})
        assert cleaned == {"document_id": 12}

        cleaned = registry.validate_args(
            registry.get("list_notifications"), {"unread_only": "false"}
        )
        assert cleaned == {"unread_only": False}

    def test_validate_args_rejects_missing_and_enum(self):
        registry = get_tool_registry()

        with pytest.raises(ToolArgumentError):
            registry.validate_args(registry.get("get_document_detail"), {})

        with pytest.raises(ToolArgumentError):
            registry.validate_args(registry.get("list_my_collections"), {"status": 9})

    def test_execute_blocks_unauthorized_role(self):
        """即使模型伪造参数，执行层也会按服务端角色拦截"""
        registry = get_tool_registry()
        spec = registry.get("class_students")
        ctx = ToolContext(
            user_id=1, username="student", role_code="student", security_level=1,
        )

        result = registry.execute(spec, ctx, {"class_id": 1})

        assert result["ok"] is False
        assert "无权" in result["summary"]


class TestIntentGate:
    def test_task_questions_enter_tool_chain(self):
        assert should_use_tools("帮我找一下 ESP32 的课件")
        assert should_use_tools("我的补采进度到哪了")
        assert should_use_tools("我想提交一个工单")
        assert should_use_tools("帮我生成班级学情周报")
        assert should_use_tools("现在有哪些文档待审核")
        assert should_use_tools("最近哪些问题答不上来")

    def test_pure_qa_stays_on_rag(self):
        assert not should_use_tools("什么是中断")
        assert not should_use_tools("I2C 的时序是怎样的")
        assert not should_use_tools("你好")


class TestTeacherInsightTools:
    def test_class_insights_respect_teaching_assignment(self, db, roles):
        """班级学情工具统计正确，且未任教教师无法查看"""
        suffix = uuid.uuid4().hex[:6]
        dept = Department(name=f"测试班_{suffix}", dept_type="class")
        db.add(dept)
        db.flush()

        teacher = User(
            username=f"teacher_{suffix}", password_hash="x",
            role_id=roles["teacher"].id,
        )
        other_teacher = User(
            username=f"teacher2_{suffix}", password_hash="x",
            role_id=roles["teacher"].id,
        )
        s1 = User(
            username=f"stu1_{suffix}", password_hash="x",
            role_id=roles["student"].id, department=dept.name,
        )
        s2 = User(
            username=f"stu2_{suffix}", password_hash="x",
            role_id=roles["student"].id, department=dept.name,
        )
        db.add_all([teacher, other_teacher, s1, s2])
        db.flush()
        db.add(TeachingAssignment(teacher_id=teacher.id, class_id=dept.id))
        db.add_all([
            ChatLog(session_id="s1", user_id=s1.id,
                    question="I2C 通信时序怎么配置", is_answered=1),
            ChatLog(session_id="s2", user_id=s2.id,
                    question="I2C 地址怎么设置", is_answered=0),
            ChatLog(session_id="s2", user_id=s2.id,
                    question="SPI 通信时序是怎样的", is_answered=1),
        ])
        db.commit()

        registry = get_tool_registry()
        ctx = ToolContext(
            user_id=teacher.id, username=teacher.username, role_code="teacher",
        )

        hot = registry.execute(
            registry.get("class_question_hotspots"), ctx,
            {"class_id": dept.id, "days": 7},
        )
        assert hot["ok"] is True
        assert hot["data"]["student_total"] == 2
        assert hot["data"]["active_students"] == 2
        assert hot["data"]["question_count"] == 3

        gaps = registry.execute(
            registry.get("class_unanswered_questions"), ctx,
            {"class_id": dept.id, "days": 7},
        )
        assert gaps["ok"] is True
        assert len(gaps["data"]["items"]) == 1

        report = registry.execute(
            registry.get("class_teaching_report"), ctx,
            {"class_id": dept.id, "days": 7},
        )
        assert report["ok"] is True
        assert report["data"]["question_count"] == 3
        assert report["data"]["unanswered_count"] == 1

        denied = registry.execute(
            registry.get("class_question_hotspots"),
            ToolContext(
                user_id=other_teacher.id,
                username=other_teacher.username,
                role_code="teacher",
            ),
            {"class_id": dept.id},
        )
        assert denied["ok"] is False
        assert "任教" in denied["summary"]

    def test_student_profile_rejects_other_class(self, db, roles):
        """学生画像只允许查本班学生"""
        suffix = uuid.uuid4().hex[:6]
        dept = Department(name=f"测试班_{suffix}", dept_type="class")
        other_dept = Department(name=f"测试班B_{suffix}", dept_type="class")
        db.add_all([dept, other_dept])
        db.flush()

        teacher = User(
            username=f"teacher_{suffix}", password_hash="x",
            role_id=roles["teacher"].id,
        )
        outsider = User(
            username=f"stu_{suffix}", password_hash="x",
            role_id=roles["student"].id, department=other_dept.name,
        )
        db.add_all([teacher, outsider])
        db.flush()
        db.add(TeachingAssignment(teacher_id=teacher.id, class_id=dept.id))
        db.commit()

        registry = get_tool_registry()
        result = registry.execute(
            registry.get("student_learning_profile"),
            ToolContext(
                user_id=teacher.id, username=teacher.username, role_code="teacher",
            ),
            {"class_id": dept.id, "student_id": outsider.id},
        )
        assert result["ok"] is False
        assert "不属于" in result["summary"]


class TestAdminOperationsTools:
    def test_all_admin_tools_run_on_empty_data(self):
        """运营工具在无数据时也应正常返回，不抛异常"""
        registry = get_tool_registry()
        ctx = ToolContext(user_id=1, username="admin", role_code="super_admin")
        cases = [
            ("list_pending_documents", {}),
            ("list_pending_work", {}),
            ("knowledge_gap_report", {"days": 7}),
            ("platform_usage_stats", {"days": 7}),
            ("account_overview", {"days": 30}),
            ("audit_summary", {"days": 7}),
        ]
        for name, args in cases:
            result = registry.execute(registry.get(name), ctx, args)
            assert result["ok"] is True, f"{name}: {result.get('summary')}"


class TestCollectionTool:
    def test_submit_is_idempotent(self):
        """同一问题在未关闭状态下重复提交不会生成多条需求"""
        registry = get_tool_registry()
        spec = registry.get("submit_collection_request")
        ctx = ToolContext(
            user_id=9999, username="tester", role_code="student", security_level=1,
        )
        question = f"测试补采幂等问题_{uuid.uuid4().hex}"

        first = spec.handler(ctx, {"question": question})
        second = spec.handler(ctx, {"question": question})

        assert first["ok"] is True
        assert first["data"]["duplicated"] is False
        assert second["ok"] is True
        assert second["data"]["duplicated"] is True
        assert second["data"]["id"] == first["data"]["id"]


class TestActionToken:
    """写操作确认令牌：参数不进入 JWT、一次性消费、防伪造"""

    def _ctx(self):
        return ToolContext(
            user_id=9998, username="tester", role_code="student", security_level=1,
            session_id="csess_test",
        )

    def test_long_chinese_args_keep_token_small(self, db):
        """500 字中文参数也不应撑爆 4000 字符接口上限"""
        from app.agent.actions import create_action_token

        question = "帮我提交补采：" + "ESP32 蓝牙配网失败怎么办？" * 40
        token = create_action_token(
            self._ctx(), "submit_collection_request", {"question": question}
        )
        assert len(token) < 2000, f"token 过长: {len(token)}"

    def test_consume_once_and_replay_rejected(self, db):
        from app.agent.actions import consume_action_token, create_action_token
        from app.core.exceptions import ValidationException

        question = f"测试确认令牌_{uuid.uuid4().hex}"
        ctx = self._ctx()
        token = create_action_token(
            ctx, "submit_collection_request", {"question": question},
            session_id=ctx.session_id,
        )

        payload = consume_action_token(token)
        assert payload["sub"] == "9998"
        assert payload["tool"] == "submit_collection_request"
        assert payload["args"]["question"] == question
        assert payload["sid"] == "csess_test"

        # 重放（含跨"重启"语义：状态在数据库而非进程内存）
        with pytest.raises(ValidationException, match="已执行"):
            consume_action_token(token)

    def test_wrong_user_rejected_without_burning(self, db):
        """他人令牌被拒，且令牌不被消费（归属校验先于消费）"""
        from app.agent.actions import consume_action_token, create_action_token
        from app.core.exceptions import ValidationException

        token = create_action_token(self._ctx(), "create_ticket", {"title": "x"})
        with pytest.raises(ValidationException, match="无权"):
            consume_action_token(token, expected_user_id=7777)
        # 令牌未被烧毁，本人仍可正常消费
        payload = consume_action_token(token, expected_user_id=9998)
        assert payload["tool"] == "create_ticket"

    def test_unknown_jti_rejected(self, db):
        import json as _json

        from app.agent.actions import consume_action_token
        from app.core.exceptions import ValidationException
        from app.core.security import create_access_token

        token = create_access_token(
            subject="9998",
            extra_claims={"typ": "agent_action", "jti": uuid.uuid4().hex},
        )
        with pytest.raises(ValidationException, match="过期"):
            consume_action_token(token)

    def test_expired_row_rejected(self, db):
        from datetime import timedelta

        from app.agent.actions import consume_action_token, create_action_token
        from app.core.exceptions import ValidationException
        from app.db.sqlite import SessionLocal
        from app.models.agent_action import AgentActionToken
        from app.models.user import utcnow

        token = create_action_token(self._ctx(), "create_ticket", {"title": "x"})
        # 直接把库内过期时间改到过去，模拟 5 分钟过期
        s = SessionLocal()
        row = s.query(AgentActionToken).order_by(
            AgentActionToken.created_at.desc()
        ).first()
        row.expires_at = utcnow() - timedelta(seconds=1)
        s.commit()
        s.close()

        with pytest.raises(ValidationException, match="过期"):
            consume_action_token(token)
