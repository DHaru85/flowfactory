"""单测默认 join eager，避免 start_run 立即返回时断言未完成。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from settings.config import reset_settings


@pytest.fixture(autouse=True)
def _join_eager_runs(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FLOWFACTORY_CELERY_EAGER_JOIN", "true")
    reset_settings()
    yield
    reset_settings()
