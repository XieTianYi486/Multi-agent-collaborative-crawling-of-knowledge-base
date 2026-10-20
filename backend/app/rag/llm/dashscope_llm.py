# ============================================================
# LLM 对话封装（支持 DashScope / DeepSeek，OpenAI 兼容接口）
# 支持同步和流式两种输出方式
# ============================================================

import json
import time
from typing import AsyncGenerator, Dict, List, Optional

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import LLMException


# 各平台默认 base_url
_PROVIDER_BASE_URLS = {
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


class ChatLLM:
    """
    通用 LLM 调用封装（OpenAI 兼容接口）

    通过 LLM_PROVIDER 切换平台:
      - dashscope: 阿里云百炼 qwen-plus (默认)
      - deepseek: DeepSeek deepseek-chat
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS

        # API Key: 优先用 LLM_API_KEY，否则回退到 DASHSCOPE_API_KEY（向后兼容）
        api_key = settings.LLM_API_KEY
        if not api_key and self.provider == "dashscope":
            api_key = settings.DASHSCOPE_API_KEY
        if not api_key:
            raise LLMException(f"未配置 LLM API Key (provider={self.provider})")
        self.api_key = api_key

        # base_url: 优先用 LLM_BASE_URL，否则按 provider 自动选
        base_url = settings.LLM_BASE_URL or _PROVIDER_BASE_URLS.get(
            self.provider, _PROVIDER_BASE_URLS["dashscope"])

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
        )
        print(f"[LLM] provider={self.provider}, model={self.model}, base_url={base_url}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """
        同步对话（非流式）

        参数:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
            temperature: 生成温度
            max_tokens: 最大 token 数

        返回:
            {"content": "回答文本", "usage": {"prompt_tokens": ..., "completion_tokens": ...}}
        """
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                stream=False,
            )

            choice = response.choices[0]
            return {
                "content": choice.message.content or "",
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
            }

        except Exception as e:
            raise LLMException(f"LLM 调用失败: {str(e)}")

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        usage_out: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式对话（返回 token 生成器）

        使用方式:
            async for token in llm.chat_stream(messages):
                yield f"data: {json.dumps({'token': token})}\n\n"
        """
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )

            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
                # include_usage 模式下末尾会有一个 usage 块（choices 为空）：
                # 提取真实 token 用量，供问答日志成本统计（避免流式路径用量恒为 0）
                if chunk.usage and usage_out is not None:
                    usage_out["prompt_tokens"] = chunk.usage.prompt_tokens or 0
                    usage_out["completion_tokens"] = chunk.usage.completion_tokens or 0
                    usage_out["total_tokens"] = chunk.usage.total_tokens or 0

        except Exception as e:
            raise LLMException(f"LLM 流式调用失败: {str(e)}")


# --- 全局单例 ---
_llm_instance: Optional[ChatLLM] = None


def get_llm() -> ChatLLM:
    """获取 LLM 客户端单例"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatLLM()
    return _llm_instance
