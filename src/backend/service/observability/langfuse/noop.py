"""关闭 LangFuse 时的空实现。"""

from __future__ import annotations

from service.observability.schemas import LlmUsageMetrics, ToolTraceRecord


class NoOpLangfuseReporter:
    def report_generation(self, metrics: LlmUsageMetrics) -> None:
        return None

    def report_tool(self, record: ToolTraceRecord) -> None:
        return None

    def shutdown(self) -> None:
        return None
