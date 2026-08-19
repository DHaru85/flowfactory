"""官方 LangFuse SDK 适配。缺配置不在 import 期崩溃。"""

from __future__ import annotations

from loguru import logger

from service.observability.schemas import LlmUsageMetrics, ToolTraceRecord
from settings.config import get_settings


class SdkLangfuseReporter:
    """仅在 langfuse_enabled 且密钥齐全时真正发网。"""

    def __init__(
        self,
        *,
        host: str | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        cfg = get_settings()
        self._host = host if host is not None else cfg.langfuse_host
        self._public_key = public_key if public_key is not None else cfg.langfuse_public_key
        self._secret_key = secret_key if secret_key is not None else cfg.langfuse_secret_key
        self._client: object | None = None

    def _ensure_client(self) -> object | None:
        if self._client is not None:
            return self._client
        if not self._public_key or not self._secret_key:
            logger.warning("LangFuse 密钥不完整，跳过上报")
            return None
        try:
            from langfuse import Langfuse
        except ImportError:
            logger.error("未安装 langfuse，跳过上报")
            return None
        kwargs: dict[str, str] = {
            "public_key": self._public_key,
            "secret_key": self._secret_key,
        }
        if self._host:
            kwargs["host"] = self._host
        self._client = Langfuse(**kwargs)
        return self._client

    def report_generation(self, metrics: LlmUsageMetrics) -> None:
        client = self._ensure_client()
        if client is None:
            return
        usage = {
            "input": metrics.prompt_tokens,
            "output": metrics.completion_tokens,
        }
        try:
            generation = getattr(client, "generation", None)
            if callable(generation):
                generation(
                    trace_id=metrics.trace_id,
                    name="llm",
                    model=metrics.model,
                    usage=usage,
                    metadata={"latency_ms": metrics.latency_ms, "cost_usd": metrics.cost_usd},
                )
                return
            create_event = getattr(client, "create_event", None)
            if callable(create_event):
                create_event(
                    name="generation",
                    metadata={
                        "trace_id": metrics.trace_id,
                        "model": metrics.model,
                        "usage": usage,
                    },
                )
        except Exception:
            logger.exception("LangFuse generation 上报失败")

    def report_tool(self, record: ToolTraceRecord) -> None:
        client = self._ensure_client()
        if client is None:
            return
        try:
            span = getattr(client, "span", None)
            if callable(span):
                span(
                    trace_id=record.trace_id,
                    name=record.tool_code,
                    metadata={
                        "success": record.success,
                        "latency_ms": record.latency_ms,
                        "input_summary": record.input_summary,
                        "output_summary": record.output_summary,
                    },
                )
                return
            create_event = getattr(client, "create_event", None)
            if callable(create_event):
                create_event(
                    name="tool",
                    metadata={"trace_id": record.trace_id, "tool_code": record.tool_code},
                )
        except Exception:
            logger.exception("LangFuse tool 上报失败")

    def shutdown(self) -> None:
        client = self._client
        if client is None:
            return
        flush = getattr(client, "flush", None)
        if callable(flush):
            try:
                flush()
            except Exception:
                logger.exception("LangFuse flush 失败")
        shutdown = getattr(client, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                logger.exception("LangFuse shutdown 失败")
