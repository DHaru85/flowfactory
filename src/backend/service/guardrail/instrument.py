"""LangGraph 节点编译期护栏包装。"""

from __future__ import annotations

from collections.abc import Callable
from inspect import iscoroutinefunction
from typing import TypeVar

from service.guardrail.context import get_current_evaluator
from service.guardrail.schemas import GuardrailCheckInput
from service.observability.redact import redact_text
from service.runtime.constants import NODE_LLM
from settings.config import get_settings

S = TypeVar("S")
NodeFn = Callable[[S], object]


def wrap_guardrail_node(node_id: str, kind: str, fn: NodeFn, *, is_entry: bool) -> NodeFn:
    """无 Evaluator 或关闭开关时透传。block 由 Evaluator 抛 GuardrailBlockedError。"""
    if not get_settings().guardrail_enabled:
        return fn

    async def _run(state: S) -> object:
        evaluator = get_current_evaluator()
        working: object = state
        if evaluator is not None and is_entry:
            text = _input_text(_as_mapping(working))
            result = await evaluator.check_input(
                GuardrailCheckInput(text=text, stage="input", context=evaluator.context)
            )
            if result.action == "mask" and result.masked_text is not None:
                working = _mask_input_state(_as_mapping(working), result.masked_text)
        inner_out = await _call_node(fn, working)
        if evaluator is not None and kind == NODE_LLM:
            mapping = _as_mapping(inner_out) if isinstance(inner_out, dict) else {}
            text = _output_text(mapping)
            checked = await evaluator.check_output(
                GuardrailCheckInput(text=text, stage="output", context=evaluator.context)
            )
            if checked.action == "mask" and checked.masked_text is not None and mapping:
                inner_out = _mask_output_state(mapping, checked.masked_text)
        return inner_out

    return _run


async def _call_node(fn: NodeFn, state: object) -> object:
    if iscoroutinefunction(fn):
        return await fn(state)  # type: ignore[misc, arg-type]
    return fn(state)  # type: ignore[arg-type, return-value]


def _as_mapping(state: object) -> dict[str, object]:
    if isinstance(state, dict):
        return dict(state)
    return {}


def _input_text(state: dict[str, object]) -> str:
    parts: list[str] = []
    messages = state.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if isinstance(item, dict):
                parts.append(str(item.get("content") or ""))
    variables = state.get("variables")
    if isinstance(variables, dict):
        for key in ("input", "user_input"):
            value = variables.get(key)
            if value:
                parts.append(str(value))
    return "\n".join(part for part in parts if part)


def _output_text(state: dict[str, object]) -> str:
    variables = state.get("variables")
    if isinstance(variables, dict) and variables.get("last_output"):
        return str(variables["last_output"])
    messages = state.get("messages")
    if isinstance(messages, list):
        for item in reversed(messages):
            if isinstance(item, dict) and str(item.get("role") or "") == "assistant":
                return str(item.get("content") or "")
    return ""


def _mask_input_state(state: dict[str, object], masked: str) -> dict[str, object]:
    """无法按字段精确回写时，将 variables.input 置为整段脱敏文本。"""
    updated = dict(state)
    variables = (
        dict(updated.get("variables") or {})
        if isinstance(updated.get("variables"), dict)
        else {}
    )
    messages = updated.get("messages")
    if isinstance(messages, list) and messages:
        new_messages: list[object] = []
        for item in messages:
            if not isinstance(item, dict):
                new_messages.append(item)
                continue
            row = dict(item)
            original = str(row.get("content") or "")
            if original:
                row["content"] = _overlap_mask(original, masked)
            new_messages.append(row)
        updated["messages"] = new_messages
    if variables.get("input"):
        variables["input"] = _overlap_mask(str(variables["input"]), masked)
    if variables.get("user_input"):
        variables["user_input"] = _overlap_mask(str(variables["user_input"]), masked)
    updated["variables"] = variables
    return updated


def _mask_output_state(state: dict[str, object], masked: str) -> dict[str, object]:
    updated = dict(state)
    variables = (
        dict(updated.get("variables") or {})
        if isinstance(updated.get("variables"), dict)
        else {}
    )
    variables["last_output"] = masked
    updated["variables"] = variables
    messages = updated.get("messages")
    if isinstance(messages, list) and messages:
        new_messages: list[object] = []
        last_assistant = True
        for item in reversed(messages):
            if (
                last_assistant
                and isinstance(item, dict)
                and str(item.get("role") or "") == "assistant"
            ):
                row = dict(item)
                row["content"] = masked
                new_messages.append(row)
                last_assistant = False
                continue
            new_messages.append(item)
        new_messages.reverse()
        updated["messages"] = new_messages
    return updated


def _overlap_mask(original: str, masked_all: str) -> str:
    if original in masked_all:
        start = masked_all.find(original)
        if start >= 0:
            return masked_all[start : start + len(original)]
    return redact_text(original)
