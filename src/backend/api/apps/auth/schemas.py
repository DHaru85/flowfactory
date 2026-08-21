"""鉴权 HTTP 请求体。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


class RegisterBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutBody(BaseModel):
    refresh_token: str | None = None


class AppVisibilityOut(BaseModel):
    app_key: str
    name: str
    can_use: bool
    can_control: bool


class UserOut(BaseModel):
    id: UUID
    username: str
    display_name: str
    status: str
    organization_id: UUID
    department_id: UUID | None
    is_superuser: bool
    last_login_at: datetime | None


class UserStatusPatch(BaseModel):
    status: Literal["active", "disabled", "banned"]
