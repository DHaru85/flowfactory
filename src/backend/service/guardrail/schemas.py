"""内容护栏序列化对象。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

GuardrailStage = Literal["input", "output"]
GuardrailAction = Literal["allow", "block", "mask"]
ViolationAction = Literal["block", "mask", "log"]


class GuardrailCheckInput(BaseModel):
    text: str
    stage: GuardrailStage
    context: dict[str, object] | None = None


class GuardrailCheckOutput(BaseModel):
    passed: bool
    action: GuardrailAction
    masked_text: str | None = None
    violated_rule_codes: list[str] = Field(default_factory=list)


class GuardrailHit(BaseModel):
    rule_code: str
    rule_id: UUID | None = None
    action: ViolationAction
    excerpt: str
    rule_type: str = ""
    stage: GuardrailStage | None = None
