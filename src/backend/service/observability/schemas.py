"""可观测性序列化对象。"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class SpanAttributesPayload(BaseModel):
    run_id: UUID | None = None
    flow_id: UUID | None = None
    node_id: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class LlmUsageMetrics(BaseModel):
    trace_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_usd: float | None = None


class ToolTraceRecord(BaseModel):
    trace_id: str
    tool_code: str
    input_summary: str
    output_summary: str | None = None
    latency_ms: int
    success: bool


class TraceContext(BaseModel):
    run_id: UUID | None = None
    conversation_id: UUID | None = None
    user_id: UUID | None = None
    flow_id: UUID | None = None
    name: str = "langgraph.run"


class PromptMessage(BaseModel):
    role: str
    content: str
