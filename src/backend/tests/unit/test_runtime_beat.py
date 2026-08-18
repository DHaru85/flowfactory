"""Beat cron 窗口与未配置系统用户时跳过。"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
