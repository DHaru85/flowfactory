"""LangFuse 工厂与 SDK 构造。"""

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.observability.langfuse.factory import (  # noqa: E402
    get_langfuse_reporter,
    set_langfuse_reporter_override,
)
from service.observability.langfuse.fake import FakeLangfuseReporter  # noqa: E402
from service.observability.langfuse.noop import NoOpLangfuseReporter  # noqa: E402
from service.observability.langfuse.sdk import SdkLangfuseReporter  # noqa: E402
from service.observability.schemas import LlmUsageMetrics, ToolTraceRecord  # noqa: E402
from settings.config import get_settings, reset_settings  # noqa: E402


def test_default_reporter_is_noop() -> None:
    reset_settings()
    assert get_settings().langfuse_enabled is False
    set_langfuse_reporter_override(None)
    reporter = get_langfuse_reporter()
    assert isinstance(reporter, NoOpLangfuseReporter)
    reporter.report_generation(
        LlmUsageMetrics(
            trace_id="abc",
            model="m",
            prompt_tokens=1,
            completion_tokens=2,
            latency_ms=3,
        )
    )


def test_fake_reporter_records() -> None:
    fake = FakeLangfuseReporter()
    set_langfuse_reporter_override(fake)
    try:
        reporter = get_langfuse_reporter()
        metrics = LlmUsageMetrics(
            trace_id="t1",
            model="qwen",
            prompt_tokens=10,
            completion_tokens=4,
            latency_ms=12,
        )
        reporter.report_generation(metrics)
        reporter.report_tool(
            ToolTraceRecord(
                trace_id="t1",
                tool_code="search",
                input_summary="q",
                output_summary="ok",
                latency_ms=5,
                success=True,
            )
        )
        assert fake.generations[0].model == "qwen"
        assert fake.tools[0].tool_code == "search"
    finally:
        set_langfuse_reporter_override(None)


def test_sdk_reporter_constructs_without_keys() -> None:
    reporter = SdkLangfuseReporter(host="", public_key="", secret_key="")
    reporter.report_generation(
        LlmUsageMetrics(
            trace_id=str(uuid4()),
            model="m",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
        )
    )
    reporter.shutdown()
