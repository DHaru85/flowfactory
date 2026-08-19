"""LangGraph 节点编译期包装。"""

from __future__ import annotations

from collections.abc import Callable
from inspect import iscoroutinefunction
from typing import TypeVar

from service.observability.collector import get_current_collector
from service.observability.schemas import SpanAttributesPayload
from settings.config import get_settings

S = TypeVar("S")
NodeFn = Callable[[S], object]


def wrap_graph_node(node_id: str, kind: str, fn: NodeFn) -> NodeFn:
    """无活跃 Collector 时透传；HITL GraphInterrupt 不标 error。"""
    if not get_settings().otel_enabled:
        return fn
    extra = {"kind": kind}

    if iscoroutinefunction(fn):
        async def _async(state: S) -> object:
            collector = get_current_collector()
            if collector is None:
                return await fn(state)  # type: ignore[misc]
            with collector.record_span(
                node_id, SpanAttributesPayload(node_id=node_id, extra=extra)
            ):
                return await fn(state)  # type: ignore[misc]

        return _async

    def _sync(state: S) -> object:
        collector = get_current_collector()
        if collector is None:
            return fn(state)
        with collector.record_span(
            node_id, SpanAttributesPayload(node_id=node_id, extra=extra)
        ):
            return fn(state)

    return _sync
