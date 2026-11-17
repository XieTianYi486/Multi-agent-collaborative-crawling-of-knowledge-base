# ============================================================
# 工具注册表
#
# 每个工具声明：名称、描述、JSON Schema、可用角色、风险级别。
# Agent 只能看到当前角色有权的工具；真正执行前还会再校验一次权限，
# 避免模型通过伪造参数越权调用。
# ============================================================

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from app.db.sqlite import SessionLocal
from app.services.audit_service import add_audit_log

logger = logging.getLogger(__name__)

RISK_READ = "read"
RISK_WRITE = "write"

# 所有业务角色（与 roles.code 保持一致）
ALL_ROLES: FrozenSet[str] = frozenset({
    "super_admin", "knowledge_admin", "dept_admin", "employee", "teacher", "student",
})
# 可查看班级/学生的角色
TEACHER_VIEW_ROLES: FrozenSet[str] = frozenset({
    "teacher", "dept_admin", "super_admin", "knowledge_admin",
})
# 可使用运营/管理类工具的角色
ADMIN_ROLES: FrozenSet[str] = frozenset({
    "super_admin", "knowledge_admin", "dept_admin",
})


class ToolPermissionError(Exception):
    """当前角色无权调用该工具"""


class ToolArgumentError(Exception):
    """工具参数不合法"""


@dataclass(frozen=True)
class ToolContext:
    """一次工具调用所依赖的用户上下文（全部来自服务端登录态）"""

    user_id: int
    username: str
    role_code: str
    security_level: int = 1
    session_id: Optional[str] = None


@dataclass(frozen=True)
class ToolSpec:
    """工具声明"""

    name: str
    description: str
    parameters: Dict[str, Any]
    roles: FrozenSet[str]
    risk: str
    handler: Callable[[ToolContext, Dict[str, Any]], Dict[str, Any]]
    label: str = ""

    def openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _truncate(value: Any, limit: int = 160) -> Any:
    """审计参数时截断长文本，避免把整篇提问写进日志"""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, dict):
        return {k: _truncate(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v, limit) for v in value[:5]]
    return value


class ToolRegistry:
    """工具白名单与执行入口"""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    # ---------- 注册与查询 ----------

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise RuntimeError(f"工具重复注册: {spec.name}")
        if spec.risk not in (RISK_READ, RISK_WRITE):
            raise ValueError(f"未知工具风险级别: {spec.risk}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def all(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def for_role(self, role_code: str) -> List[ToolSpec]:
        return [t for t in self._tools.values() if role_code in t.roles]

    def openai_tools(self, role_code: str) -> List[Dict[str, Any]]:
        return [t.openai_schema() for t in self.for_role(role_code)]

    def is_allowed(self, name: str, role_code: str) -> bool:
        spec = self._tools.get(name)
        return spec is not None and role_code in spec.roles

    # ---------- 参数校验 ----------

    @staticmethod
    def _coerce(value: Any, expected: str) -> Any:
        """把模型常见的字符串化参数转换成声明类型"""
        if expected == "string":
            if isinstance(value, (dict, list)):
                raise ToolArgumentError("参数类型应为字符串")
            return str(value)
        if expected == "integer":
            if isinstance(value, bool):
                raise ToolArgumentError("参数类型应为整数")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                return int(value.strip())
            raise ToolArgumentError("参数类型应为整数")
        if expected == "number":
            if isinstance(value, bool):
                raise ToolArgumentError("参数类型应为数字")
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    pass
            raise ToolArgumentError("参数类型应为数字")
        if expected == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in ("true", "false"):
                return value.lower() == "true"
            raise ToolArgumentError("参数类型应为布尔值")
        if expected == "array":
            if not isinstance(value, list):
                raise ToolArgumentError("参数类型应为数组")
            return value
        if expected == "object":
            if not isinstance(value, dict):
                raise ToolArgumentError("参数类型应为对象")
            return value
        return value

    def validate_args(self, spec: ToolSpec, args: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(args, dict):
            raise ToolArgumentError("工具参数必须是 JSON 对象")

        schema = spec.parameters or {}
        properties: Dict[str, Any] = schema.get("properties", {})
        required = schema.get("required", [])

        for key in required:
            if args.get(key) in (None, ""):
                raise ToolArgumentError(f"缺少必填参数：{key}")

        cleaned: Dict[str, Any] = {}
        for key, value in args.items():
            if key not in properties:
                continue  # 丢弃模型臆造的参数
            prop = properties[key]
            coerced = self._coerce(value, prop.get("type", "string"))
            if prop.get("enum") is not None and coerced not in prop["enum"]:
                raise ToolArgumentError(f"{key} 取值不在允许范围内")
            cleaned[key] = coerced
        return cleaned

    # ---------- 执行 ----------

    def execute(
        self, spec: ToolSpec, ctx: ToolContext, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工具并写审计日志。

        返回统一结构：{"ok": bool, "summary": str, "data": dict,
                      "sources": list (可选), "resources": list (可选)}
        """
        started = time.time()
        status = "success"
        error: Optional[str] = None

        if ctx.role_code not in spec.roles:
            status = "blocked"
            error = "当前角色无权调用该工具"
            result = {"ok": False, "summary": error, "data": {"error": error}}
        else:
            try:
                clean_args = self.validate_args(spec, args)
                result = spec.handler(ctx, clean_args)
                if not isinstance(result, dict):
                    result = {"ok": True, "summary": str(result), "data": {}}
                if not result.get("ok", True):
                    status = "failure"
            except ToolArgumentError as e:
                status = "failure"
                error = str(e)
                result = {"ok": False, "summary": f"参数不合法：{e}", "data": {"error": str(e)}}
            except ToolPermissionError as e:
                status = "blocked"
                error = str(e)
                result = {"ok": False, "summary": str(e), "data": {"error": str(e)}}
            except Exception as e:  # 工具内部异常不应打断整轮对话
                status = "failure"
                error = f"{type(e).__name__}: {e}"
                logger.warning("工具执行失败 %s: %s", spec.name, error)
                result = {
                    "ok": False,
                    "summary": "工具执行失败，请稍后重试或换个问法",
                    "data": {"error": error},
                }

        elapsed = round((time.time() - started) * 1000)
        self._audit(spec, ctx, args, status, elapsed, error)
        return result

    @staticmethod
    def _audit(
        spec: ToolSpec,
        ctx: ToolContext,
        args: Dict[str, Any],
        status: str,
        elapsed_ms: int,
        error: Optional[str],
    ) -> None:
        db = SessionLocal()
        try:
            add_audit_log(
                db=db,
                module="counselor_agent",
                action="tool_call",
                status=status,
                user_id=ctx.user_id,
                username=ctx.username,
                target_type="agent_tool",
                target_id=spec.name,
                detail={
                    "tool": spec.name,
                    "risk": spec.risk,
                    "args": _truncate(args or {}),
                    "elapsed_ms": elapsed_ms,
                    "error": _truncate(error or ""),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("写入工具调用审计失败", exc_info=True)
        finally:
            db.close()


# --- 全局单例 ---
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表（首次调用时加载工具实现）"""
    global _registry
    if _registry is None:
        registry = ToolRegistry()
        # 延迟导入，避免 tools -> registry -> tools 的循环引用
        from app.agent import tools as _tools  # noqa: F401

        _tools.register_all(registry)
        _registry = registry
    return _registry
