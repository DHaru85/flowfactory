"""模型应用 HTTP 序列化对象。"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

_SECRET_KEYS = frozenset({"api_key", "apiKey"})


def redact_llm_config(config: dict[str, object]) -> tuple[dict[str, object], bool]:
    """去掉密钥字段；返回公开 config 与是否曾有密钥。"""
    has_api_key = False
    public: dict[str, object] = {}
    for key, value in config.items():
        if key in _SECRET_KEYS:
            if isinstance(value, str) and value:
                has_api_key = True
            continue
        public[key] = value
    return public, has_api_key


class LlmCreateBody(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    model_name: str = Field(min_length=1, max_length=128)
    config: dict[str, object] = Field(default_factory=dict)
    is_active: bool = True


class LlmPatchBody(BaseModel):
    provider: str | None = Field(default=None, max_length=32)
    model_name: str | None = Field(default=None, max_length=128)
    config: dict[str, object] | None = None
    is_active: bool | None = None


class LlmOut(BaseModel):
    id: UUID
    code: str
    provider: str
    model_name: str
    is_active: bool
    config: dict[str, object]
    has_api_key: bool
