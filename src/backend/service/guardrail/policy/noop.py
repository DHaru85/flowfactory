"""未配置远程策略时的空实现。"""

from __future__ import annotations

from service.guardrail.schemas import GuardrailHit, GuardrailStage


class NoOpPolicyDetector:
    async def detect(self, text: str, stage: GuardrailStage) -> list[GuardrailHit]:
        return []
