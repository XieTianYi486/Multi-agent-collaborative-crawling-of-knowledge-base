"""任务→模型档位注册表（config/models.yaml 驱动）与 Provider 单例管理。

测试可调用 set_chat_provider() 注入 Fake Provider。
"""
from __future__ import annotations

from ..settings import ModelSpec, load_models
from .base import ChatProvider
from .dashscope_provider import DashScopeChatProvider

_NO_PROVIDER = object()  # 哨兵：强制无 Provider（测试用）

_override: ChatProvider | object | None = None
_dashscope: DashScopeChatProvider | None = None
_dashscope_failed = False


def get_spec(task: str) -> ModelSpec | None:
    """任务对应的模型档位（未配置返回 None）。"""
    return load_models().get(task)


def set_chat_provider(provider: ChatProvider | None) -> None:
    """注入 Provider（测试用）。

    - 传 Provider 实例 → 强制使用该实例（屏蔽真实 API）；
    - 传 None → 强制无 Provider（LLM 步骤全部跳过，不触网）。
    """
    global _override
    _override = provider if provider is not None else _NO_PROVIDER


def reset_chat_provider() -> None:
    """恢复默认（真实的 DashScope Provider）。"""
    global _override
    _override = None


def get_chat_provider() -> ChatProvider | None:
    """当前可用 Provider；强制无 Provider 或未配置 API Key 时返回 None。"""
    global _dashscope, _dashscope_failed
    if _override is _NO_PROVIDER:
        return None
    if _override is not None:
        return _override
    if _dashscope is None and not _dashscope_failed:
        try:
            _dashscope = DashScopeChatProvider()
        except RuntimeError:
            _dashscope_failed = True  # 未配置 key：不再重复尝试
    return _dashscope


def get_batch_client():
    """批量客户端；Provider 不可用返回 None。"""
    provider = get_chat_provider()
    if provider is None or not isinstance(provider, DashScopeChatProvider):
        return None
    from .batch import BatchClient

    return BatchClient(provider._client)  # noqa: SLF001 - 同包内部访问
