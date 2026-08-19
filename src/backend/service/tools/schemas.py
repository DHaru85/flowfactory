"""工具调用序列化对象。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    tool_call_id: str
    tool_code: str
    arguments: dict[str, object] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    tool_call_id: str
    success: bool
    output: object | None = None
    error: str | None = None
