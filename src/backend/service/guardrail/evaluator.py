"""GuardrailEvaluator：进程内评估 + 违规缓冲。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.security.models import PolicyViolation
from service.guardrail.errors import GuardrailBlockedError
from service.guardrail.policy.factory import get_policy_detector
from service.guardrail.policy.protocol import PolicyDetector
from service.guardrail.rules import RuleSpec, apply_masks, match_rule, merge_action
from service.guardrail.schemas import (
    GuardrailCheckInput,
    GuardrailCheckOutput,
    GuardrailHit,
    GuardrailStage,
)
from service.observability.redact import redact_text
from service.persistence.factory import get_repositories
from settings.config import get_settings


class GuardrailEvaluator:
    def __init__(
        self,
        specs: list[RuleSpec],
        *,
        context: dict[str, object] | None = None,
        detector: PolicyDetector | None = None,
    ) -> None:
        self._specs = specs
        self._context = context or {}
        self._detector = detector
        self._hits: list[GuardrailHit] = []
        self._chunk_buffer = ""

    @property
    def context(self) -> dict[str, object]:
        return self._context

    def _excerpt_limit(self) -> int:
        return get_settings().guardrail_excerpt_max_chars

    def _specs_for(self, stage: GuardrailStage) -> list[RuleSpec]:
        return [item for item in self._specs if item.stage == stage]

    async def check_input(self, payload: GuardrailCheckInput) -> GuardrailCheckOutput:
        return await self._check(payload)

    async def check_output(self, payload: GuardrailCheckInput) -> GuardrailCheckOutput:
        return await self._check(payload)

    def consume_chunk(self, text: str) -> None:
        self._chunk_buffer += text

    async def finalize_output(self) -> GuardrailCheckOutput:
        result = await self.check_output(
            GuardrailCheckInput(text=self._chunk_buffer, stage="output", context=self._context)
        )
        self._chunk_buffer = ""
        return result

    async def _check(self, payload: GuardrailCheckInput) -> GuardrailCheckOutput:
        cfg = get_settings()
        if not cfg.guardrail_enabled:
            return GuardrailCheckOutput(passed=True, action="allow")
        hits: list[GuardrailHit] = []
        for spec in self._specs_for(payload.stage):
            hits.extend(match_rule(spec, payload.text, excerpt_limit=self._excerpt_limit()))
        detector = self._detector if self._detector is not None else get_policy_detector()
        remote = await detector.detect(payload.text, payload.stage)
        hits.extend(remote)
        if not hits:
            return GuardrailCheckOutput(passed=True, action="allow", masked_text=payload.text)
        self._hits.extend(hits)
        decision = merge_action(hits)
        codes = [hit.rule_code for hit in hits]
        if decision == "block":
            raise GuardrailBlockedError(codes)
        masked = apply_masks(payload.text, hits) if decision == "mask" else payload.text
        passed = decision != "block"
        action = "mask" if decision == "mask" else "allow"
        return GuardrailCheckOutput(
            passed=passed,
            action=action,
            masked_text=masked,
            violated_rule_codes=codes,
        )

    async def flush(self, session: AsyncSession) -> int:
        if not self._hits:
            return 0
        repos = get_repositories(session)
        written = 0
        for hit in self._hits:
            if hit.rule_id is None:
                continue
            user_id = _as_uuid(self._context.get("user_id"))
            run_id = _as_uuid(self._context.get("run_id"))
            conversation_id = _as_uuid(self._context.get("conversation_id"))
            await repos.security.record_violation(
                PolicyViolation(
                    rule_id=hit.rule_id,
                    user_id=user_id,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    stage=hit.stage or _stage_of(hit, self._specs),
                    matched_excerpt=redact_text(hit.excerpt) if hit.excerpt else None,
                    action_taken=hit.action,
                )
            )
            written += 1
        self._hits.clear()
        return written


def _stage_of(hit: GuardrailHit, specs: list[RuleSpec]) -> str:
    for spec in specs:
        if spec.code == hit.rule_code:
            return spec.stage
    return "output"


def _as_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None
