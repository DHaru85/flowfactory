"""HITL 状态流转（仓储 mock）。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.constants import (  # noqa: E402
    HITL_APPROVED,
    HITL_PENDING,
    HITL_REJECTED,
    RUN_CANCELLED,
)
from service.runtime.hitl import apply_resume_decision  # noqa: E402
from service.runtime.schemas import HitlResumeInput  # noqa: E402


@pytest.mark.asyncio
async def test_apply_resume_reject_cancels_run(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl_id = uuid4()
    run_id = uuid4()
    pending = SimpleNamespace(
        id=hitl_id,
        run_id=run_id,
        status=HITL_PENDING,
        resume_payload=None,
        resolved_at=None,
    )
    run = SimpleNamespace(id=run_id, status="interrupted", finished_at=None)
    repos = SimpleNamespace(
        workflow=SimpleNamespace(
            hitl=SimpleNamespace(get=AsyncMock(return_value=pending)),
            run=SimpleNamespace(get=AsyncMock(return_value=run)),
        )
    )
    monkeypatch.setattr(
        "service.runtime.hitl.get_repositories",
        lambda _session: repos,
    )
    monkeypatch.setattr("service.runtime.hitl.touch_run_active", lambda *_a, **_k: None)

    session = MagicMock()
    _pending, _run, output = await apply_resume_decision(
        session,
        HitlResumeInput(hitl_id=hitl_id, decision="reject"),
    )
    assert output.resumed is False
    assert pending.status == HITL_REJECTED
    assert run.status == RUN_CANCELLED
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_apply_resume_approve(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl_id = uuid4()
    run_id = uuid4()
    pending = SimpleNamespace(
        id=hitl_id,
        run_id=run_id,
        status=HITL_PENDING,
        resume_payload=None,
        resolved_at=None,
    )
    run = SimpleNamespace(id=run_id, status="interrupted", finished_at=None)
    repos = SimpleNamespace(
        workflow=SimpleNamespace(
            hitl=SimpleNamespace(get=AsyncMock(return_value=pending)),
            run=SimpleNamespace(get=AsyncMock(return_value=run)),
        )
    )
    monkeypatch.setattr(
        "service.runtime.hitl.get_repositories",
        lambda _session: repos,
    )
    monkeypatch.setattr("service.runtime.hitl.touch_run_active", lambda *_a, **_k: None)
    _p, _r, output = await apply_resume_decision(
        MagicMock(),
        HitlResumeInput(hitl_id=hitl_id, decision="approve", user_input="go"),
    )
    assert output.resumed is True
    assert pending.status == HITL_APPROVED
    assert pending.resume_payload is not None
