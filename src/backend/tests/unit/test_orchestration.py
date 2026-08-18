"""外层编排工厂。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.orchestration.factory import get_orchestrator  # noqa: E402
from service.orchestration.passthrough import PassthroughOrchestrator  # noqa: E402
from service.orchestration.temporal.orchestrator import TemporalOrchestrator  # noqa: E402
from settings.config import reset_settings  # noqa: E402


def test_default_orchestrator_is_passthrough() -> None:
    reset_settings()
    orch = get_orchestrator()
    assert isinstance(orch, PassthroughOrchestrator)


def test_temporal_orchestrator_class_exists() -> None:
    assert TemporalOrchestrator is not None
