"""OpenAI 兼容聊天客户端（vLLM）。"""

from __future__ import annotations

from time import perf_counter
from typing import Protocol

from loguru import logger
from openai import AsyncOpenAI

from service.observability.observe import observe_chat_completion
from settings.config import get_settings

ChatMessage = dict[str, str]


class ChatCompletionClient(Protocol):
    async def complete(self, messages: list[ChatMessage]) -> str:
        """根据消息列表生成助手回复。"""


class OpenAICompatClient:
    """对接 vLLM OpenAI 接口。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        cfg = get_settings()
        self._model = model or cfg.llm_model_name
        self._client = AsyncOpenAI(
            base_url=base_url or cfg.llm_base_url,
            api_key=api_key if api_key is not None else cfg.llm_api_key_or_empty_placeholder,
        )

    async def complete(self, messages: list[ChatMessage]) -> str:
        payload = messages or [{"role": "user", "content": ""}]
        logger.debug("调用 LLM model={} messages={}", self._model, len(payload))
        started = perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=payload,  # type: ignore[arg-type]
            )
        except Exception as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            observe_chat_completion(
                payload,
                model=self._model,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc),
            )
            raise
        latency_ms = int((perf_counter() - started) * 1000)
        usage = response.usage
        prompt_tokens = int(usage.prompt_tokens) if usage and usage.prompt_tokens else 0
        completion_tokens = (
            int(usage.completion_tokens) if usage and usage.completion_tokens else 0
        )
        choice = response.choices[0].message
        content = choice.content or ""
        observe_chat_completion(
            payload,
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status="ok",
        )
        return content


class FakeChatCompletionClient:
    """单元测试替身。"""

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        observe_chat_completion(
            messages,
            model="fake",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            status="ok",
        )
        return self.reply


_override: ChatCompletionClient | None = None


def set_chat_client_override(client: ChatCompletionClient | None) -> None:
    global _override
    _override = client


def get_chat_client() -> ChatCompletionClient:
    if _override is not None:
        return _override
    return OpenAICompatClient()
