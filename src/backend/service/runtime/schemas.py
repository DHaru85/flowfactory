"""工作流运行时序列化对象（对齐 data_schema_server.md）。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RunStatePayload(BaseModel):
    """LangGraph state 业务载荷。"""

    messages: list[dict[str, object]] = Field(default_factory=list)
    variables: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_graph_state(self) -> dict[str, object]:
        return {
            "messages": list(self.messages),
            "variables": dict(self.variables),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_graph_state(cls, state: dict[str, object]) -> "RunStatePayload":
        raw_messages = state.get("messages") or []
        raw_variables = state.get("variables") or {}
        raw_metadata = state.get("metadata") or {}
        messages = [dict(m) for m in raw_messages] if isinstance(raw_messages, list) else []
        variables = dict(raw_variables) if isinstance(raw_variables, dict) else {}
        metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        return cls(messages=messages, variables=variables, metadata=metadata)


class ThreadContextPayload(BaseModel):
    queue_name: str
    priority: int = 0
    worker_affinity: str | None = None


class HitlResumeInput(BaseModel):
    hitl_id: UUID
    decision: Literal["approve", "reject"]
    user_input: str | None = None


class HitlResumeOutput(BaseModel):
    run_id: UUID
    resumed: bool


class FlowDefinitionDocument(BaseModel):
    nodes: list[dict[str, object]]
    edges: list[dict[str, object]]
    entry_point: str
    interrupt_before: list[str] = Field(default_factory=list)


class CeleryTaskEnvelope(BaseModel):
    task_name: str
    run_id: UUID
    flow_id: UUID
    thread_id: UUID
    langgraph_thread_id: str
    input_payload: RunStatePayload
    resume: HitlResumeInput | None = None


class BeatTaskTriggerPayload(BaseModel):
    beat_task_id: UUID
    flow_id: UUID
    input_payload: dict[str, object] = Field(default_factory=dict)
    scheduled_at: datetime


class StartRunRequest(BaseModel):
    user_id: UUID
    flow_id: UUID
    input_payload: RunStatePayload
    conversation_id: UUID | None = None
    queue_name: str | None = None
    priority: int = 0
    definition: FlowDefinitionDocument | None = None
