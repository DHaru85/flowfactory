"""Agent 配置 HTTP 序列化对象。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ResourceType = Literal["profile", "skill", "tool", "mcp_server"]
SubjectType = Literal["organization", "department", "role", "user"]
ToolKind = Literal["builtin", "http", "mcp"]
McpTransport = Literal["stdio", "sse"]


class BindingItem(BaseModel):
    subject_type: SubjectType
    subject_id: UUID
    actions: list[str] = Field(default_factory=lambda: ["read", "use"])


class BindingPutBody(BaseModel):
    bindings: list[BindingItem]


class ProfileCreateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    system_prompt: str
    default_llm_id: UUID | None = None
    skill_ids: list[UUID] = Field(default_factory=list)


class ProfilePatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    system_prompt: str | None = None
    default_llm_id: UUID | None = None
    skill_ids: list[UUID] | None = None


class ProfileOut(BaseModel):
    id: UUID
    code: str
    name: str
    system_prompt: str
    default_llm_id: UUID | None
    skill_ids: list[UUID]


class SkillCreateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    tool_ids: list[UUID] = Field(default_factory=list)
    prompt_template: str | None = None


class SkillPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    tool_ids: list[UUID] | None = None
    prompt_template: str | None = None


class SkillOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    tool_ids: list[UUID]
    prompt_template: str | None


class ToolCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    kind: ToolKind
    parameter_schema: dict[str, object] = Field(alias="schema")
    config: dict[str, object] = Field(default_factory=dict)
    mcp_server_id: UUID | None = None


class ToolPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, max_length=128)
    kind: ToolKind | None = None
    parameter_schema: dict[str, object] | None = Field(default=None, alias="schema")
    config: dict[str, object] | None = None
    mcp_server_id: UUID | None = None


class ToolOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    id: UUID
    code: str
    name: str
    kind: str
    parameter_schema: dict[str, object] = Field(alias="schema")
    config: dict[str, object]
    mcp_server_id: UUID | None


class McpCreateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    transport: McpTransport
    config: dict[str, object]
    is_active: bool = True


class McpPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    transport: McpTransport | None = None
    config: dict[str, object] | None = None
    is_active: bool | None = None


class McpOut(BaseModel):
    id: UUID
    code: str
    name: str
    transport: str
    config: dict[str, object]
    is_active: bool


class BeatCreateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    flow_id: UUID | None = None
    profile_id: UUID | None = None
    cron: str = Field(min_length=1, max_length=64)
    input_payload: dict[str, object] = Field(default_factory=dict)
    is_enabled: bool = True


class BeatPatchBody(BaseModel):
    cron: str | None = Field(default=None, max_length=64)
    input_payload: dict[str, object] | None = None


class BeatOut(BaseModel):
    id: UUID
    code: str
    flow_id: UUID | None
    profile_id: UUID | None
    cron: str
    input_payload: dict[str, object]
    is_enabled: bool
    last_triggered_at: datetime | None
