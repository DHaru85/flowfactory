"""鉴权 HTTP 请求体。"""

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutBody(BaseModel):
    refresh_token: str | None = None


class AppVisibilityOut(BaseModel):
    app_key: str
    name: str
    can_use: bool
    can_control: bool
