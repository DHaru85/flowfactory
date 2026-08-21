"""工作流编排 Studio REST。

本轮：校验并持久化 schema_version=1；应用两档权限。执行走 runtime compile 双读。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from loguru import logger
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.access import require_app
from api.apps.agent_config.access import load_visible_profile_rows, load_visible_tool_rows
from api.apps.studio.schemas import (
    FlowCreateBody,
    FlowOut,
    FlowPatchBody,
    LlmCatalogOut,
    ProfileCatalogOut,
    PublishedFlowCodeOut,
    ToolCatalogOut,
)
from api.deps import CurrentUser, db_session
from api.errors import http_error
from data_schema.agent.models import AgentFlow
from service.persistence.factory import get_repositories
from service.runtime.definition_v1 import (
    FlowDefinitionV1,
    empty_flow_definition,
    parse_flow_definition,
    subgraph_flow_codes,
)

router = APIRouter(prefix="/api/v1/studio", tags=["studio"])

_use_studio = require_app("studio")
_ctrl_studio = require_app("studio", control=True)


def _parse_definition(raw: dict[str, object]) -> FlowDefinitionV1:
    try:
        return parse_flow_definition(raw)
    except ValidationError as exc:
        raise http_error(400, "definition_invalid", str(exc)) from exc
    except ValueError as exc:
        raise http_error(400, "definition_invalid", str(exc)) from exc


def _try_out(row: AgentFlow) -> FlowOut | None:
    raw = dict(row.definition)
    if raw.get("schema_version") != 1:
        logger.warning("列表跳过非 v1 Flow id={}", row.id)
        return None
    return FlowOut(
        id=row.id,
        code=row.code,
        name=row.name,
        version=row.version,
        profile_id=row.profile_id,
        status=row.status,
        published_at=row.published_at,
        definition=_parse_definition(raw),
    )


def _to_out(row: AgentFlow) -> FlowOut:
    item = _try_out(row)
    if item is None:
        raise http_error(
            400,
            "flow_definition_not_v1",
            "该工作流不是 schema_version=1，Studio 本轮不可编辑",
        )
    return item


async def _get_flow(session: AsyncSession, flow_id: UUID) -> AgentFlow:
    repos = get_repositories(session)
    flow = await repos.agent.flow.get(flow_id)
    if flow is None or flow.status == "deleted":
        raise http_error(404, "flow_not_found", "工作流不存在")
    return flow


async def _require_profile(session: AsyncSession, profile_id: UUID) -> None:
    repos = get_repositories(session)
    profile = await repos.agent.profile.get(profile_id)
    if profile is None:
        raise http_error(400, "profile_not_found", "Profile 不存在")


async def _assert_subgraph_refs_and_no_cycle(
    session: AsyncSession,
    *,
    flow_code: str,
    document: FlowDefinitionV1,
) -> None:
    repos = get_repositories(session)
    visiting: set[str] = {flow_code}

    async def _walk(code: str, definition: FlowDefinitionV1) -> None:
        for ref in subgraph_flow_codes(definition):
            if ref in visiting:
                raise http_error(
                    400,
                    "definition_invalid",
                    f"子图 flow_code 编译期成环: {ref}",
                )
            published = await repos.agent.get_latest_published_flow(ref)
            if published is None:
                raise http_error(
                    400,
                    "definition_invalid",
                    f"子图目标未发布: {ref}",
                )
            visiting.add(ref)
            child = _parse_definition(dict(published.definition))
            await _walk(ref, child)
            visiting.remove(ref)

    await _walk(flow_code, document)


@router.get("/profiles", response_model=list[ProfileCatalogOut])
async def list_profiles(
    current: CurrentUser = Depends(_use_studio),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ProfileCatalogOut]:
    rows = await load_visible_profile_rows(session, current.id, offset=offset, limit=limit)
    return [ProfileCatalogOut(id=row.id, code=row.code, name=row.name) for row in rows]


@router.get("/llms", response_model=list[LlmCatalogOut])
async def list_llms(
    current: CurrentUser = Depends(_use_studio),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[LlmCatalogOut]:
    repos = get_repositories(session)
    rows = await repos.agent.llm.list(offset=offset, limit=limit)
    return [
        LlmCatalogOut(
            id=row.id,
            code=row.code,
            provider=row.provider,
            model_name=row.model_name,
        )
        for row in rows
        if row.is_active
    ]


@router.get("/tools", response_model=list[ToolCatalogOut])
async def list_tools(
    current: CurrentUser = Depends(_use_studio),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ToolCatalogOut]:
    rows = await load_visible_tool_rows(session, current.id, offset=offset, limit=limit)
    return [
        ToolCatalogOut(id=row.id, code=row.code, name=row.name, kind=row.kind) for row in rows
    ]


@router.get("/flows/published-codes", response_model=list[PublishedFlowCodeOut])
async def list_published_codes(
    current: CurrentUser = Depends(_use_studio),
    session: AsyncSession = Depends(db_session),
) -> list[PublishedFlowCodeOut]:
    repos = get_repositories(session)
    pairs = await repos.agent.list_published_flow_summaries()
    return [PublishedFlowCodeOut(code=code, version=version) for code, version in pairs]


@router.get("/flows", response_model=list[FlowOut])
async def list_flows(
    current: CurrentUser = Depends(_use_studio),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
    status: str | None = Query(default=None),
    code: str | None = Query(default=None),
) -> list[FlowOut]:
    repos = get_repositories(session)
    rows = await repos.agent.list_flows(offset=offset, limit=limit, status=status, code=code)
    return [item for row in rows if (item := _try_out(row)) is not None]


@router.post("/flows", response_model=FlowOut)
async def create_flow(
    body: FlowCreateBody,
    current: CurrentUser = Depends(_ctrl_studio),
    session: AsyncSession = Depends(db_session),
) -> FlowOut:
    await _require_profile(session, body.profile_id)
    document = (
        empty_flow_definition()
        if body.definition is None
        else _parse_definition(body.definition)
    )
    repos = get_repositories(session)
    flow = AgentFlow(
        code=body.code,
        name=body.name,
        version=1,
        profile_id=body.profile_id,
        definition=document.model_dump(mode="json"),
        status="draft",
        published_at=None,
    )
    try:
        await repos.agent.add_flow(flow)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "flow_code_version_conflict", "code 与 version 已存在") from exc
    logger.info("Studio 创建 Flow id={} code={}", flow.id, flow.code)
    return _to_out(flow)


@router.get("/flows/{flow_id}", response_model=FlowOut)
async def get_flow(
    flow_id: UUID,
    current: CurrentUser = Depends(_use_studio),
    session: AsyncSession = Depends(db_session),
) -> FlowOut:
    return _to_out(await _get_flow(session, flow_id))


@router.patch("/flows/{flow_id}", response_model=FlowOut)
async def patch_flow(
    flow_id: UUID,
    body: FlowPatchBody,
    current: CurrentUser = Depends(_ctrl_studio),
    session: AsyncSession = Depends(db_session),
) -> FlowOut:
    flow = await _get_flow(session, flow_id)
    if flow.status != "draft":
        raise http_error(400, "flow_not_draft", "仅草稿可修改")
    if body.profile_id is not None:
        await _require_profile(session, body.profile_id)
        flow.profile_id = body.profile_id
    if body.name is not None:
        flow.name = body.name
    if body.definition is not None:
        flow.definition = _parse_definition(body.definition).model_dump(mode="json")
    return _to_out(flow)


@router.post("/flows/{flow_id}/publish", response_model=FlowOut)
async def publish_flow(
    flow_id: UUID,
    current: CurrentUser = Depends(_ctrl_studio),
    session: AsyncSession = Depends(db_session),
) -> FlowOut:
    flow = await _get_flow(session, flow_id)
    if flow.status != "draft":
        raise http_error(400, "flow_not_draft", "仅草稿可发布")
    document = _parse_definition(dict(flow.definition))
    await _assert_subgraph_refs_and_no_cycle(
        session, flow_code=flow.code, document=document
    )
    repos = get_repositories(session)
    await repos.agent.archive_published_siblings(flow.code, flow.id)
    flow.status = "published"
    flow.published_at = datetime.now(UTC)
    logger.info("Studio 发布 Flow id={} code={} version={}", flow.id, flow.code, flow.version)
    return _to_out(flow)


@router.post("/flows/{flow_id}/new-draft", response_model=FlowOut)
async def new_draft(
    flow_id: UUID,
    current: CurrentUser = Depends(_ctrl_studio),
    session: AsyncSession = Depends(db_session),
) -> FlowOut:
    source = await _get_flow(session, flow_id)
    if source.status != "published":
        raise http_error(400, "flow_not_published", "仅已发布版本可开新草稿")
    repos = get_repositories(session)
    draft = AgentFlow(
        code=source.code,
        name=source.name,
        version=source.version + 1,
        profile_id=source.profile_id,
        definition=dict(source.definition),
        status="draft",
        published_at=None,
    )
    try:
        await repos.agent.add_flow(draft)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "flow_code_version_conflict", "下一版本已存在") from exc
    logger.info("Studio 新草稿 id={} from={}", draft.id, source.id)
    return _to_out(draft)


@router.delete("/flows/{flow_id}")
async def delete_flow(
    flow_id: UUID,
    current: CurrentUser = Depends(_ctrl_studio),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    _ = current
    flow = await _get_flow(session, flow_id)
    repos = get_repositories(session)
    if await repos.agent.count_beats_for_flow(flow.id) > 0:
        raise http_error(409, "flow_in_use", "工作流仍被定时任务引用，不可删除")
    if await repos.conversation.count_active_by_flow(flow.id) > 0:
        raise http_error(409, "flow_in_use", "工作流仍被未删除会话引用，不可删除")
    flow.status = "deleted"
    logger.info("Studio 软删 Flow id={}", flow.id)
    return {"status": "deleted"}
