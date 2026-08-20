"""OpenAI 兼容聊天客户端（vLLM）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from time import perf_counter
from typing import Literal, Protocol
from uuid import UUID

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from service.observability.observe import observe_chat_completion
from settings.config import get_settings

ChatMessage = dict[str, str]
ChatTurnMessage = dict[str, object]

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_REASONING_FIELDS = ("reasoning_content", "reasoning")


class StreamDelta(BaseModel):
    """一次流式增量：面向用户或思考。"""

    kind: Literal["speaking", "reasoning"]
    text: str


def _delta_attr_str(delta: object, names: Sequence[str]) -> str:
    extra = getattr(delta, "model_extra", None)
    mapping = extra if isinstance(extra, dict) else None
    as_dict = delta if isinstance(delta, dict) else None
    for name in names:
        value = getattr(delta, name, None) if not isinstance(delta, dict) else None
        if isinstance(value, str) and value:
            return value
        if mapping is not None:
            nested = mapping.get(name)
            if isinstance(nested, str) and nested:
                return nested
        if as_dict is not None:
            nested = as_dict.get(name)
            if isinstance(nested, str) and nested:
                return nested
    return ""


def _prefix_overlap(buf: str, token: str) -> int:
    max_n = min(len(buf), len(token) - 1)
    for n in range(max_n, 0, -1):
        if buf.endswith(token[:n]):
            return n
    return 0


class ThinkTagSplitter:
    """把正文里的 <think>…</think> 拆成 reasoning / speaking。"""

    def __init__(self) -> None:
        self._buf = ""
        self._in_think: bool | None = None

    def feed(self, piece: str) -> list[StreamDelta]:
        if not piece:
            return []
        self._buf += piece
        out: list[StreamDelta] = []
        while self._buf:
            if self._in_think is None:
                if self._buf.startswith(_THINK_OPEN):
                    self._in_think = True
                    self._buf = self._buf[len(_THINK_OPEN) :]
                    continue
                if _THINK_OPEN.startswith(self._buf):
                    break
                self._in_think = False
            if self._in_think:
                idx = self._buf.find(_THINK_CLOSE)
                if idx == -1:
                    hold = _prefix_overlap(self._buf, _THINK_CLOSE)
                    emit = self._buf if hold == 0 else self._buf[:-hold]
                    self._buf = "" if hold == 0 else self._buf[-hold:]
                    if emit:
                        out.append(StreamDelta(kind="reasoning", text=emit))
                    break
                if idx:
                    out.append(StreamDelta(kind="reasoning", text=self._buf[:idx]))
                self._buf = self._buf[idx + len(_THINK_CLOSE) :]
                self._in_think = False
                continue
            out.append(StreamDelta(kind="speaking", text=self._buf))
            self._buf = ""
            break
        return out

    def flush(self) -> list[StreamDelta]:
        leftover = self._buf
        self._buf = ""
        if not leftover:
            return []
        kind: Literal["speaking", "reasoning"] = (
            "reasoning" if self._in_think is True else "speaking"
        )
        return [StreamDelta(kind=kind, text=leftover)]


def _message_reasoning(message: object) -> str:
    return _delta_attr_str(message, _REASONING_FIELDS)


def _split_think_content(raw: str) -> tuple[str, str]:
    splitter = ThinkTagSplitter()
    parts = [*splitter.feed(raw), *splitter.flush()]
    reasoning = "".join(p.text for p in parts if p.kind == "reasoning")
    speaking = "".join(p.text for p in parts if p.kind == "speaking")
    return speaking, reasoning


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
    reasoning: str = ""
    tool_calls: list[ToolCallSpec] = Field(default_factory=list)


class ChatCompletionClient(Protocol):
    async def complete(self, messages: list[ChatMessage]) -> str:
        """根据消息列表生成助手回复。"""

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """面向用户的 token 增量；不经内容护栏。"""

    def stream_parts(self, messages: list[ChatMessage]) -> AsyncIterator[StreamDelta]:
        """speaking / reasoning 增量；不经内容护栏。"""

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
        resolved = (base_url or cfg.llm_base_url).strip()
        if not (resolved.startswith("http://") or resolved.startswith("https://")):
            raise ValueError(f"LLM base_url 须为 http(s) URL，当前: {resolved!r}")
        self._base_url = resolved
        self._client = AsyncOpenAI(
            base_url=resolved,
            api_key=api_key if api_key is not None else cfg.llm_api_key_or_empty_placeholder,
        )

    async def complete(self, messages: list[ChatMessage]) -> str:
        parts: list[str] = []
        async for delta in self.stream(messages):
            parts.append(delta)
        return "".join(parts)

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        async for part in self.stream_parts(messages):
            if part.kind == "speaking" and part.text:
                yield part.text

    async def stream_parts(self, messages: list[ChatMessage]) -> AsyncIterator[StreamDelta]:
        payload = messages or [{"role": "user", "content": ""}]
        logger.debug(
            "流式调用 LLM model={} base_url={} messages={}",
            self._model,
            self._base_url,
            len(payload),
        )
        started = perf_counter()
        prompt_tokens = 0
        completion_tokens = 0
        splitter = ThinkTagSplitter()
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
                reasoning = _delta_attr_str(delta, _REASONING_FIELDS)
                if reasoning:
                    yield StreamDelta(kind="reasoning", text=reasoning)
                content = getattr(delta, "content", None)
                if isinstance(content, str) and content:
                    for part in splitter.feed(content):
                        yield part
            for part in splitter.flush():
                yield part
        except Exception as exc:
            logger.warning(
                "LLM 流式调用失败 model={} base_url={} err={}",
                self._model,
                self._base_url,
                exc,
            )
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
            speaking: list[str] = []
            reasoning: list[str] = []
            async for part in self.stream_parts(text_msgs):
                if part.kind == "reasoning":
                    reasoning.append(part.text)
                else:
                    speaking.append(part.text)
            return ChatTurn(content="".join(speaking), reasoning="".join(reasoning))
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
            reasoning_text = _message_reasoning(choice)
            if _THINK_OPEN in raw_content and not reasoning_text:
                raw_content, reasoning_text = _split_think_content(raw_content)
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
        return ChatTurn(content=raw_content, reasoning=reasoning_text, tool_calls=calls)


class FakeChatCompletionClient:
    """单元测试替身。"""

    def __init__(
        self,
        reply: str = "ok",
        chunks: list[str] | None = None,
        reasoning_chunks: list[str] | None = None,
        turns: list[ChatTurn] | None = None,
    ) -> None:
        self.reply = reply
        self.chunks = chunks
        self.reasoning_chunks = list(reasoning_chunks or [])
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
        async for part in self.stream_parts(messages):
            if part.kind == "speaking" and part.text:
                yield part.text

    async def stream_parts(self, messages: list[ChatMessage]) -> AsyncIterator[StreamDelta]:
        self.calls.append(messages)
        for piece in self.reasoning_chunks:
            yield StreamDelta(kind="reasoning", text=piece)
        pieces = self.chunks if self.chunks is not None else [self.reply]
        for piece in pieces:
            yield StreamDelta(kind="speaking", text=piece)
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
        speaking: list[str] = []
        reasoning: list[str] = []
        async for part in self.stream_parts(
            [
                {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
                for item in messages
            ]
        ):
            if part.kind == "reasoning":
                reasoning.append(part.text)
            else:
                speaking.append(part.text)
        return ChatTurn(content="".join(speaking), reasoning="".join(reasoning))


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
