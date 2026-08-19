"""内存 LangFuse 替身。"""

from __future__ import annotations

from service.observability.schemas import LlmUsageMetrics, ToolTraceRecord


class FakeLangfuseReporter:
    def __init__(self) -> None:
        self.generations: list[LlmUsageMetrics] = []
        self.tools: list[ToolTraceRecord] = []
        self.shutdown_calls: int = 0

    def report_generation(self, metrics: LlmUsageMetrics) -> None:
        self.generations.append(metrics)

    def report_tool(self, record: ToolTraceRecord) -> None:
        self.tools.append(record)

    def shutdown(self) -> None:
        self.shutdown_calls += 1
