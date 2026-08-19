"""OpenTelemetry TraceCollector：进程内采集并 flush 到 obs_*。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode, set_span_in_context
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.observability.models import (
    ObsLlmCall,
    ObsPromptSnapshot,
    ObsSpan,
    ObsToolInvocation,
    ObsTrace,
)
from service.observability.langfuse.factory import get_langfuse_reporter
from service.observability.redact import hash_content, redact_text
from service.observability.schemas import (
    LlmUsageMetrics,
    PromptMessage,
    SpanAttributesPayload,
    ToolTraceRecord,
    TraceContext,
)
from service.persistence.factory import get_repositories
from settings.config import get_settings

_KIND_NAME = {
    SpanKind.INTERNAL: "internal",
    SpanKind.CLIENT: "client",
    SpanKind.SERVER: "server",
    SpanKind.PRODUCER: "client",
    SpanKind.CONSUMER: "server",
}

_current_collector: ContextVar[TraceCollector | None] = ContextVar(
    "flowfactory_trace_collector",
    default=None,
)


def get_current_collector() -> TraceCollector | None:
    return _current_collector.get()


def attach_collector(collector: TraceCollector) -> Token[TraceCollector | None]:
    return _current_collector.set(collector)


def reset_collector(token: Token[TraceCollector | None]) -> None:
    _current_collector.reset(token)


def reset_observability_context() -> None:
    """Celery prefork 后丢弃父进程 ContextVar。"""
    _current_collector.set(None)


class _CollectingSpanProcessor(SpanProcessor):
    def __init__(self) -> None:
        self.ended: list[ReadableSpan] = []

    def on_start(self, span: object, parent_context: object = None) -> None:
        return None

    def on_end(self, span: ReadableSpan) -> None:
        self.ended.append(span)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


@dataclass
class _LlmBuffer:
    span_id: str
    trace_id: str
    run_id: UUID | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    status: str
    error_message: str | None
    cost_usd: float | None
    messages: list[PromptMessage]


@dataclass
class _ToolBuffer:
    span_id: str
    run_id: UUID | None
    record: ToolTraceRecord


def _format_trace_id(trace_id: int) -> str:
    return format(trace_id, "032x")


def _format_span_id(span_id: int) -> str:
    return format(span_id, "016x")


def _ns_to_dt(nanos: int | None) -> datetime | None:
    if nanos is None:
        return None
    return datetime.fromtimestamp(nanos / 1_000_000_000, tz=UTC)


def _maybe_graph_interrupt(exc: BaseException) -> bool:
    return type(exc).__name__ in {"GraphInterrupt", "NodeInterrupt"}


def _attr_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class TraceCollector:
    """一条业务 run / 一次 ainvoke 对应一个 Collector。"""

    def __init__(self) -> None:
        cfg = get_settings()
        resource = Resource.create({"service.name": cfg.otel_service_name})
        self._processor = _CollectingSpanProcessor()
        self._provider = TracerProvider(resource=resource)
        self._provider.add_span_processor(self._processor)
        endpoint = cfg.otel_otlp_endpoint.strip()
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            self._provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            )
        self._tracer = trace.get_tracer("flowfactory.trace", tracer_provider=self._provider)
        self._root: trace.Span | None = None
        self._otel_token: object | None = None
        self._context = TraceContext()
        self._status = "ok"
        self._name = "langgraph.run"
        self._started_at = datetime.now(UTC)
        self._finished_at: datetime | None = None
        self._llm: list[_LlmBuffer] = []
        self._tools: list[_ToolBuffer] = []

    def start_trace(self, name: str, context: TraceContext) -> str:
        self._name = name
        self._context = context
        self._started_at = datetime.now(UTC)
        self._root = self._tracer.start_span(name, kind=SpanKind.INTERNAL)
        self._root.set_attribute("run_id", str(context.run_id) if context.run_id else "")
        self._root.set_attribute(
            "conversation_id", str(context.conversation_id) if context.conversation_id else ""
        )
        self._root.set_attribute("user_id", str(context.user_id) if context.user_id else "")
        if context.flow_id:
            self._root.set_attribute("flow_id", str(context.flow_id))
        self._otel_token = attach(set_span_in_context(self._root))
        return self.trace_id

    @property
    def trace_id(self) -> str:
        if self._root is None:
            ended = self._processor.ended
            if ended:
                return _format_trace_id(ended[0].context.trace_id)
            return ""
        return _format_trace_id(self._root.get_span_context().trace_id)

    def current_span_id(self) -> str:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            return _format_span_id(ctx.span_id)
        if self._root is not None:
            return _format_span_id(self._root.get_span_context().span_id)
        return ""

    def end_trace(self, status: str) -> None:
        self._status = status if status in {"ok", "error"} else "error"
        self._finished_at = datetime.now(UTC)
        if self._root is not None:
            if self._status == "error":
                self._root.set_status(Status(StatusCode.ERROR))
            self._root.end()
            self._root = None
        if self._otel_token is not None:
            detach(self._otel_token)
            self._otel_token = None

    @contextmanager
    def record_span(
        self, name: str, attributes: SpanAttributesPayload | None = None
    ) -> Iterator[None]:
        parent = trace.get_current_span()
        span = self._tracer.start_span(
            name[:128],
            context=set_span_in_context(parent),
            kind=SpanKind.INTERNAL,
        )
        payload = attributes or SpanAttributesPayload()
        if payload.run_id:
            span.set_attribute("run_id", str(payload.run_id))
        if payload.flow_id:
            span.set_attribute("flow_id", str(payload.flow_id))
        if payload.node_id:
            span.set_attribute("node_id", payload.node_id)
        for key, value in payload.extra.items():
            span.set_attribute(key, value)
        token = attach(set_span_in_context(span))
        try:
            yield
        except BaseException as exc:
            if not _maybe_graph_interrupt(exc):
                span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            span.end()
            detach(token)

    def record_llm_call(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        messages: list[PromptMessage],
        status: str = "ok",
        error_message: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        ctx = trace.get_current_span().get_span_context()
        trace_id = self.trace_id or (
            _format_trace_id(ctx.trace_id) if ctx.is_valid else ""
        )
        item = _LlmBuffer(
            span_id=self.current_span_id(),
            trace_id=trace_id,
            run_id=self._context.run_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
            cost_usd=cost_usd,
            messages=messages,
        )
        self._llm.append(item)
        metrics = LlmUsageMetrics(
            trace_id=item.trace_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
        try:
            get_langfuse_reporter().report_generation(metrics)
        except Exception:
            logger.exception("LangFuse generation 上报异常")

    def record_tool(self, record: ToolTraceRecord) -> None:
        self._tools.append(
            _ToolBuffer(
                span_id=self.current_span_id(),
                run_id=self._context.run_id,
                record=record,
            )
        )
        try:
            get_langfuse_reporter().report_tool(record)
        except Exception:
            logger.exception("LangFuse tool 上报异常")

    def ended_span_names(self) -> list[str]:
        return [span.name for span in self._processor.ended]

    def pending_llm_count(self) -> int:
        return len(self._llm)

    def pending_tool_count(self) -> int:
        return len(self._tools)

    async def flush(self, session: AsyncSession) -> None:
        self._provider.force_flush()
        if not self._processor.ended:
            return
        otel_trace_id = _format_trace_id(self._processor.ended[0].context.trace_id)
        repos = get_repositories(session)
        existing = await repos.observability.get_trace_by_otel_id(otel_trace_id)
        if existing is None:
            await repos.observability.trace.add(
                ObsTrace(
                    trace_id=otel_trace_id,
                    run_id=self._context.run_id,
                    conversation_id=self._context.conversation_id,
                    user_id=self._context.user_id,
                    name=self._name[:128],
                    status=self._status,
                    started_at=self._started_at,
                    finished_at=self._finished_at or datetime.now(UTC),
                )
            )
        for span in self._processor.ended:
            span_id = _format_span_id(span.context.span_id)
            if await repos.observability.get_span_by_span_id(span_id) is not None:
                continue
            parent = None
            if span.parent is not None:
                parent = _format_span_id(span.parent.span_id)
            started = _ns_to_dt(span.start_time) or self._started_at
            finished = _ns_to_dt(span.end_time)
            duration = None
            if span.start_time is not None and span.end_time is not None:
                duration = int((span.end_time - span.start_time) / 1_000_000)
            attributes: dict[str, object] = {}
            if span.attributes:
                attributes = {str(k): _attr_value(v) for k, v in span.attributes.items()}
            await repos.observability.span.add(
                ObsSpan(
                    trace_id=_format_trace_id(span.context.trace_id),
                    span_id=span_id,
                    parent_span_id=parent,
                    name=(span.name or "")[:128],
                    kind=_KIND_NAME.get(span.kind, "internal"),
                    attributes=attributes,
                    started_at=started,
                    finished_at=finished,
                    duration_ms=duration,
                )
            )
        for item in self._llm:
            call = await repos.observability.llm_call.add(
                ObsLlmCall(
                    span_id=item.span_id,
                    run_id=item.run_id,
                    model=item.model[:128],
                    prompt_tokens=item.prompt_tokens,
                    completion_tokens=item.completion_tokens,
                    latency_ms=item.latency_ms,
                    status=item.status[:16],
                    error_message=item.error_message,
                )
            )
            snapshots = [
                ObsPromptSnapshot(
                    llm_call_id=call.id,
                    role=(msg.role or "user")[:16],
                    content_redacted=redact_text(msg.content),
                    content_hash=hash_content(msg.content),
                )
                for msg in item.messages
            ]
            if snapshots:
                await repos.observability.add_prompt_snapshots(snapshots)
        for item in self._tools:
            rec = item.record
            await repos.observability.tool_invocation.add(
                ObsToolInvocation(
                    span_id=item.span_id,
                    run_id=item.run_id,
                    tool_code=rec.tool_code[:64],
                    latency_ms=rec.latency_ms,
                    success=rec.success,
                    error_message=None if rec.success else rec.output_summary,
                )
            )
        self._llm.clear()
        self._tools.clear()
