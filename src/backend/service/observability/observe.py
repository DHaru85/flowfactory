"""将聊天完成写入当前 TraceCollector。"""

from __future__ import annotations

from service.observability.collector import get_current_collector
from service.observability.schemas import PromptMessage


def observe_chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str = "ok",
    error_message: str | None = None,
) -> None:
    collector = get_current_collector()
    if collector is None:
        return
    prompts = [
        PromptMessage(role=str(item.get("role") or "user"), content=str(item.get("content") or ""))
        for item in messages
    ]
    collector.record_llm_call(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        messages=prompts,
        status=status,
        error_message=error_message,
    )
