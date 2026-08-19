"""将工具调用写入当前 TraceCollector。"""

from __future__ import annotations

import json

from service.observability.collector import get_current_collector
from service.observability.redact import redact_text
from service.observability.schemas import ToolTraceRecord


def _summary(payload: object, limit: int = 400) -> str:
    try:
        raw = json.dumps(payload, ensure_ascii=False, default=str)
    except TypeError:
        raw = str(payload)
    redacted = redact_text(raw)
    if len(redacted) <= limit:
        return redacted
    return redacted[: limit - 1] + "…"


def observe_tool_call(
    *,
    tool_code: str,
    arguments: dict[str, object],
    result_output: object | None,
    latency_ms: int,
    success: bool,
) -> None:
    collector = get_current_collector()
    if collector is None:
        return
    collector.record_tool(
        ToolTraceRecord(
            trace_id=collector.trace_id,
            tool_code=tool_code,
            input_summary=_summary(arguments),
            output_summary=_summary(result_output) if result_output is not None else None,
            latency_ms=latency_ms,
            success=success,
        )
    )
