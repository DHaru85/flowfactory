"""内存策略检测替身。"""

from __future__ import annotations

from service.guardrail.schemas import GuardrailHit, GuardrailStage


class FakePolicyDetector:
    def __init__(self, hits: list[GuardrailHit] | None = None) -> None:
        self.hits = hits or []
        self.calls: list[tuple[str, str]] = []

    async def detect(self, text: str, stage: GuardrailStage) -> list[GuardrailHit]:
        self.calls.append((text, stage))
        return list(self.hits)
