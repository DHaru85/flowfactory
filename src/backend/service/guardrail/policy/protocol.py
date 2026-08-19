"""外置策略检测协议。实现不得依赖 ORM。"""

from __future__ import annotations

from typing import Protocol

from service.guardrail.schemas import GuardrailHit, GuardrailStage


class PolicyDetector(Protocol):
    async def detect(self, text: str, stage: GuardrailStage) -> list[GuardrailHit]:
        """附加检测；失败由实现自行吞掉并返回空列表。"""
