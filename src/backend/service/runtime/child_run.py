"""子图独立 Run：环检测、回传载荷、超时点。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import RunSnapshot
from service.persistence.factory import get_repositories
from service.runtime.definition_v1 import FlowDefinitionV1, subgraph_flow_codes
from service.runtime.flow import parse_compile_document
from service.runtime.schemas import RunStatePayload, SubgraphNodeResult


async def detect_subgraph_cycle(
    session: AsyncSession,
    *,
    parent_flow_id: UUID,
    child_flow_code: str,
    child_version: int | None,
    ancestors: list[str],
) -> str | None:
    repos = get_repositories(session)
    parent = await repos.agent.flow.get(parent_flow_id)
    parent_code = parent.code if parent is not None else None
    chain = list(ancestors)
    if parent_code:
        chain.append(parent_code)
    if child_flow_code in chain:
        return f"子图 code 回环: {child_flow_code}"
    if child_version is None:
        child = await repos.agent.get_latest_published_flow(child_flow_code)
    else:
        child = await repos.agent.get_flow_by_code_version(child_flow_code, child_version)
    if child is None or child.status != "published":
        return f"子图未发布: {child_flow_code}"
    parsed = parse_compile_document(dict(child.definition))
    if not isinstance(parsed, FlowDefinitionV1):
        return None
    next_codes = subgraph_flow_codes(parsed)
    deeper = [*chain, child_flow_code]
    for code in next_codes:
        if code in deeper:
            return f"子图 code 回环: {code}"
    return None


def child_input_from_interrupt(value: dict[str, object]) -> RunStatePayload:
    raw = value.get("child_input")
    if isinstance(raw, dict):
        return RunStatePayload.from_graph_state(raw)
    return RunStatePayload()


def result_from_child_run(
    run: RunSnapshot,
    *,
    status: str,
    error: str | None = None,
) -> SubgraphNodeResult:
    output = RunStatePayload()
    if isinstance(run.output_payload, dict):
        output = RunStatePayload.from_graph_state(run.output_payload)
    mapped = status if status in {"completed", "failed", "cancelled", "timeout"} else "failed"
    return SubgraphNodeResult(
        status=mapped,  # type: ignore[arg-type]
        output=output,
        error=error or run.error_message,
    )


def timeout_at_from_seconds(seconds: object) -> datetime | None:
    if not isinstance(seconds, int) or seconds <= 0:
        return None
    return datetime.now(UTC) + timedelta(seconds=seconds)
