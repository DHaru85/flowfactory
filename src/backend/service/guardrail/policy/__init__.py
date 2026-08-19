"""外置策略检测预留。"""

from service.guardrail.policy.factory import get_policy_detector, set_policy_detector_override
from service.guardrail.policy.fake import FakePolicyDetector
from service.guardrail.policy.http import HttpPolicyDetector
from service.guardrail.policy.noop import NoOpPolicyDetector

__all__ = [
    "FakePolicyDetector",
    "HttpPolicyDetector",
    "NoOpPolicyDetector",
    "get_policy_detector",
    "set_policy_detector_override",
]
