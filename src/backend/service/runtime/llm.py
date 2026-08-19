"""OpenAI 兼容聊天客户端（vLLM）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
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

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """token 增量；不经内容护栏。"""


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
        parts: list[str] = []
        async for delta in self.stream(messages):
            parts.append(delta)
        return "".join(parts)

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        payload = messages or [{"role": "user", "content": ""}]
        logger.debug("流式调用 LLM model={} messages={}", self._model, len(payload))
        started = perf_counter()
        prompt_tokens = 0
        completion_tokens = 0
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=payload,  # type: ignore[arg-type]
                stream=True,
            )
            async for chunk in response:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                choices = chunk.choices
                if not choices:
                    continue
                delta = choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except Exception as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            observe_chat_completion(
                payload,
                model=self._model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc),
            )
            raise
        latency_ms = int((perf_counter() - started) * 1000)
        observe_chat_completion(
            payload,
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status="ok",
        )


class FakeChatCompletionClient:
    """单元测试替身。"""

    def __init__(self, reply: str = "ok", chunks: list[str] | None = None) -> None:
        self.reply = reply
        self.chunks = chunks
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: list[ChatMessage]) -> str:
        parts: list[str] = []
        async for delta in self.stream(messages):
            parts.append(delta)
        return "".join(parts)

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(messages)
        pieces = self.chunks if self.chunks is not None else [self.reply]
        for piece in pieces:
            yield piece
        observe_chat_completion(
            messages,
            model="fake",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            status="ok",
        )


_override: ChatCompletionClient | None = None


def set_chat_client_override(client: ChatCompletionClient | None) -> None:
    global _override
    _override = client


def get_chat_client() -> ChatCompletionClient:
    if _override is not None:
        return _override
    return OpenAICompatClient()
