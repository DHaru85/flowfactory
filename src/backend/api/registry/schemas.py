"""注册表序列化对象。"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationContext(BaseModel):
    app_key: str
    settings: dict[str, object] = Field(default_factory=dict)
    user_id: UUID | None = None


class ServiceInvokeContext(BaseModel):
    service_key: str
    caller_app_key: str
    request_id: str
    user_id: UUID | None = None
