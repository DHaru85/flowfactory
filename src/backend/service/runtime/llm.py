"""OpenAI 兼容聊天客户端（vLLM）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from time import perf_counter
from typing import Protocol
from uuid import UUID

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from service.observability.observe import observe_chat_completion
from settings.config import get_settings

ChatMessage = dict[str, str]
ChatTurnMessage = dict[str, object]


class ToolSpec(BaseModel):
    code: str
    name: str
    description: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)


class ToolCallSpec(BaseModel):
    id: str
    tool_code: str
    arguments: dict[str, object] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    content: str = ""
    tool_calls: list[ToolCallSpec] = Field(default_factory=list)


class ChatCompletionClient(Protocol):
    async def complete(self, messages: list[ChatMessage]) -> str:
        """根据消息列表生成助手回复。"""

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """token 增量；不经内容护栏。"""

    async def complete_turn(
        self,
        messages: Sequence[ChatTurnMessage],
        tools: Sequence[ToolSpec] | None = None,
    ) -> ChatTurn:
        """一轮：可选 function-call。"""


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

    async def complete_turn(
        self,
        messages: Sequence[ChatTurnMessage],
        tools: Sequence[ToolSpec] | None = None,
    ) -> ChatTurn:
        payload = list(messages) or [{"role": "user", "content": ""}]
        if not tools:
            text_msgs: list[ChatMessage] = []
            for item in payload:
                role = str(item.get("role") or "user")
                content = str(item.get("content") or "")
                text_msgs.append({"role": role, "content": content})
            content = await self.complete(text_msgs)
            return ChatTurn(content=content)
        tool_payload = [
            {
                "type": "function",
                "function": {
                    "name": spec.code,
                    "description": spec.description or spec.name,
                    "parameters": spec.parameters or {"type": "object", "properties": {}},
                },
            }
            for spec in tools
        ]
        started = perf_counter()
        prompt_tokens = 0
        completion_tokens = 0
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=payload,  # type: ignore[arg-type]
                tools=tool_payload,  # type: ignore[arg-type]
                stream=False,
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            choice = response.choices[0].message
            raw_content = choice.content or ""
            calls: list[ToolCallSpec] = []
            for item in choice.tool_calls or []:
                raw_args = item.function.arguments or "{}"
                try:
                    parsed = json.loads(raw_args)
                    arguments = parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    arguments = {}
                calls.append(
                    ToolCallSpec(
                        id=str(item.id),
                        tool_code=str(item.function.name),
                        arguments=arguments,
                    )
                )
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
        return ChatTurn(content=raw_content, tool_calls=calls)


class FakeChatCompletionClient:
    """单元测试替身。"""

    def __init__(
        self,
        reply: str = "ok",
        chunks: list[str] | None = None,
        turns: list[ChatTurn] | None = None,
    ) -> None:
        self.reply = reply
        self.chunks = chunks
        self.turns = list(turns or [])
        self._turn_index = 0
        self.calls: list[list[ChatMessage]] = []
        self.turn_calls: list[list[ChatTurnMessage]] = []

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

    async def complete_turn(
        self,
        messages: Sequence[ChatTurnMessage],
        tools: Sequence[ToolSpec] | None = None,
    ) -> ChatTurn:
        self.turn_calls.append(list(messages))
        _ = tools
        if self.turns:
            if self._turn_index >= len(self.turns):
                return ChatTurn(content=self.reply)
            turn = self.turns[self._turn_index]
            self._turn_index += 1
            return turn
        content = await self.complete(
            [
                {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
                for item in messages
            ]
        )
        return ChatTurn(content=content)


_override: ChatCompletionClient | None = None


def set_chat_client_override(client: ChatCompletionClient | None) -> None:
    global _override
    _override = client


def has_chat_client_override() -> bool:
    return _override is not None


def get_chat_client() -> ChatCompletionClient:
    if _override is not None:
        return _override
    return OpenAICompatClient()


def _config_str(config: dict[str, object], key: str) -> str | None:
    value = config.get(key)
    if isinstance(value, str) and value:
        return value
    return None


async def resolve_llm_client(
    *,
    llm_id: UUID | None = None,
    code: str | None = None,
) -> ChatCompletionClient:
    """按 agent_llm 解析客户端；缺省回退环境变量。测试 override 优先。"""
    if _override is not None:
        return _override
    if llm_id is None and (code is None or code == ""):
        return OpenAICompatClient()

    from service.database.session import session_scope
    from service.persistence.factory import get_repositories

    async with session_scope() as session:
        repos = get_repositories(session)
        row = None
        if llm_id is not None:
            row = await repos.agent.llm.get(llm_id)
        elif code is not None:
            row = await repos.agent.get_llm_by_code(code)
        if row is None or not row.is_active:
            ident = str(llm_id or code or "")
            raise ValueError(f"LLM 不可用: {ident}")
        cfg = row.config if isinstance(row.config, dict) else {}
        return OpenAICompatClient(
            base_url=_config_str(cfg, "base_url"),
            api_key=_config_str(cfg, "api_key"),
            model=row.model_name,
        )
