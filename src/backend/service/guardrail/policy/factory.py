"""策略检测器工厂。"""

from __future__ import annotations

from service.guardrail.policy.http import HttpPolicyDetector
from service.guardrail.policy.noop import NoOpPolicyDetector
from service.guardrail.policy.protocol import PolicyDetector
from settings.config import get_settings

_override: PolicyDetector | None = None


def set_policy_detector_override(detector: PolicyDetector | None) -> None:
    global _override
    _override = detector


def get_policy_detector() -> PolicyDetector:
    if _override is not None:
        return _override
    cfg = get_settings()
    if not cfg.guardrail_policy_url.strip():
        return NoOpPolicyDetector()
    return HttpPolicyDetector()
