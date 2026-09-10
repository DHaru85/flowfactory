"""Studio HTTP 序列化对象。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from service.runtime.definition_v1 import FlowDefinitionV1


class FlowCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    definition: dict[str, object] | None = None


class FlowPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    definition: dict[str, object] | None = None


class FlowOut(BaseModel):
    id: UUID
    code: str
    name: str
    version: int
    status: str
    published_at: datetime | None
    definition: FlowDefinitionV1


class PublishedFlowCodeOut(BaseModel):
    code: str
    version: int
    name: str


class ProfileCatalogOut(BaseModel):
    id: UUID
    code: str
    name: str


class LlmCatalogOut(BaseModel):
    id: UUID
    code: str
    provider: str
    model_name: str


class ToolCatalogOut(BaseModel):
    id: UUID
    code: str
    name: str
    kind: str
