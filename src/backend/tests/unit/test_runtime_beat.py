"""Beat cron 窗口与未配置系统用户时跳过。"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.beat import dispatch_due_tasks, is_cron_due  # noqa: E402


def test_cron_due_inside_tick_window() -> None:
    now = datetime(2026, 8, 18, 12, 0, 30, tzinfo=UTC)
    assert is_cron_due(
        "* * * * *",
        now=now,
        last_triggered_at=None,
        tick_seconds=60,
    )


def test_cron_not_due_when_already_triggered() -> None:
    now = datetime(2026, 8, 18, 12, 0, 30, tzinfo=UTC)
    last = datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)
    assert not is_cron_due(
        "* * * * *",
        now=now,
        last_triggered_at=last,
        tick_seconds=60,
    )


@pytest.mark.asyncio
async def test_dispatch_skips_without_system_user() -> None:
    session = MagicMock()
    start_run = AsyncMock()
    result = await dispatch_due_tasks(session, start_run=start_run)
    assert result == []
    start_run.assert_not_called()


def _due_task(*, flow_id=None, profile_id=None) -> MagicMock:
    task = MagicMock()
    task.id = uuid4()
    task.code = "beat-x"
    task.cron = "* * * * *"
    task.last_triggered_at = None
    task.flow_id = flow_id
    task.profile_id = profile_id
    task.input_payload = {"input": "tick"}
    return task


@pytest.mark.asyncio
async def test_dispatch_planner_does_not_load_flow() -> None:
    profile_id = uuid4()
    task = _due_task(profile_id=profile_id)
    repos = MagicMock()
    repos.agent.list_enabled_beat_tasks = AsyncMock(return_value=[task])
    repos.agent.flow.get = AsyncMock()
    start_run = AsyncMock()
    cfg = MagicMock()
    cfg.beat_system_user_uuid = uuid4()
    cfg.beat_tick_seconds = 60
    now = datetime(2026, 8, 18, 12, 0, 30, tzinfo=UTC)
    with (
        patch("service.runtime.beat.get_settings", return_value=cfg),
        patch("service.runtime.beat.get_repositories", return_value=repos),
        patch("service.runtime.beat._try_acquire_lock", return_value=True),
    ):
        triggered = await dispatch_due_tasks(
            MagicMock(), now=now, start_run=start_run
        )
    assert len(triggered) == 1
    assert triggered[0].profile_id == profile_id
    start_run.assert_awaited_once()
    req = start_run.await_args.args[0]
    assert req.kind == "planner"
    assert req.profile_id == profile_id
    repos.agent.flow.get.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_flow_still_loads_definition() -> None:
    flow_id = uuid4()
    task = _due_task(flow_id=flow_id)
    flow = MagicMock()
    flow.definition = {
        "schema_version": 0,
        "nodes": [{"id": "a", "kind": "passthrough"}],
        "edges": [{"source": "a", "target": "END"}],
        "entry_point": "a",
    }
    repos = MagicMock()
    repos.agent.list_enabled_beat_tasks = AsyncMock(return_value=[task])
    repos.agent.flow.get = AsyncMock(return_value=flow)
    start_run = AsyncMock()
    cfg = MagicMock()
    cfg.beat_system_user_uuid = uuid4()
    cfg.beat_tick_seconds = 60
    now = datetime(2026, 8, 18, 12, 0, 30, tzinfo=UTC)
    with (
        patch("service.runtime.beat.get_settings", return_value=cfg),
        patch("service.runtime.beat.get_repositories", return_value=repos),
        patch("service.runtime.beat._try_acquire_lock", return_value=True),
    ):
        triggered = await dispatch_due_tasks(
            MagicMock(), now=now, start_run=start_run
        )
    assert len(triggered) == 1
    assert triggered[0].flow_id == flow_id
    start_run.assert_awaited_once()
    req = start_run.await_args.args[0]
    assert req.kind == "flow"
    assert req.definition is not None
    repos.agent.flow.get.assert_awaited_once_with(flow_id)
