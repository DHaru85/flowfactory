"""LangFuse Reporter 工厂。"""

from __future__ import annotations

from service.observability.langfuse.noop import NoOpLangfuseReporter
from service.observability.langfuse.protocol import LangfuseReporter
from service.observability.langfuse.sdk import SdkLangfuseReporter
from settings.config import get_settings

_override: LangfuseReporter | None = None


def set_langfuse_reporter_override(reporter: LangfuseReporter | None) -> None:
    global _override
    _override = reporter


def get_langfuse_reporter() -> LangfuseReporter:
    if _override is not None:
        return _override
    cfg = get_settings()
    if not cfg.langfuse_enabled:
        return NoOpLangfuseReporter()
    return SdkLangfuseReporter()
