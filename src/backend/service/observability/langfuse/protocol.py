"""LangFuse 上报协议。实现不得依赖 ORM。"""

from __future__ import annotations

from typing import Protocol

from service.observability.schemas import LlmUsageMetrics, ToolTraceRecord


class LangfuseReporter(Protocol):
    def report_generation(self, metrics: LlmUsageMetrics) -> None:
        """上报 generation / token。"""

    def report_tool(self, record: ToolTraceRecord) -> None:
        """上报 tool span。"""

    def shutdown(self) -> None:
        """刷缓冲。"""
