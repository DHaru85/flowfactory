"""按配置选择外层编排实现。"""

from service.orchestration.passthrough import PassthroughOrchestrator
from service.orchestration.protocol import OuterOrchestrator
from settings.config import get_settings


def get_orchestrator() -> OuterOrchestrator:
    if get_settings().temporal_enabled:
        from service.orchestration.temporal.orchestrator import TemporalOrchestrator

        return TemporalOrchestrator()
    return PassthroughOrchestrator()
