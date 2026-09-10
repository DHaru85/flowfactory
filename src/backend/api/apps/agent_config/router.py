"""Agent 配置 REST：Profile / Skill / Tool / MCP / Beat。

可见可用与完全控制两档；配置行按绑定过滤。
"""

from __future__ import annotations

from uuid import UUID

from croniter import croniter
from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.access import require_app
from api.apps.agent_config.access import (
    assert_config_visible,
    drop_config_resource,
    load_bindings,
    load_visible_mcp_rows,
    load_visible_profile_rows,
    load_visible_skill_rows,
    load_visible_tool_rows,
    save_bindings,
    upsert_config_asset,
)
from api.apps.agent_config.schemas import (
    BeatCreateBody,
    BeatOut,
    BeatPatchBody,
    BindingItem,
    BindingPutBody,
    McpCreateBody,
    McpOut,
    McpPatchBody,
    ProfileCreateBody,
    ProfileOut,
    ProfilePatchBody,
    SkillCreateBody,
    SkillOut,
    SkillPatchBody,
    ToolCreateBody,
    ToolOut,
    ToolPatchBody,
)
from api.deps import CurrentUser, db_session
from api.errors import http_error
from data_schema.agent.models import (
    AgentBeatTask,
    AgentMcpServer,
    AgentProfile,
    AgentSkill,
    AgentTool,
)
from service.persistence.factory import get_repositories

router = APIRouter(prefix="/api/v1/agent-config", tags=["agent_config"])

_use_agent_config = require_app("agent_config")
_ctrl_agent_config = require_app("agent_config", control=True)


def _uuids_from_json(raw: list[str]) -> list[UUID]:
    result: list[UUID] = []
    for item in raw:
        result.append(UUID(str(item)))
    return result


def _uuid_strs(ids: list[UUID]) -> list[str]:
    return [str(item) for item in ids]


async def _require_llm(session: AsyncSession, llm_id: UUID | None) -> None:
    if llm_id is None:
        return
    repos = get_repositories(session)
    if await repos.agent.llm.get(llm_id) is None:
        raise http_error(400, "llm_not_found", "默认模型不存在")


async def _require_skills(session: AsyncSession, skill_ids: list[UUID]) -> None:
    repos = get_repositories(session)
    for skill_id in skill_ids:
        if await repos.agent.skill.get(skill_id) is None:
            raise http_error(400, "skill_not_found", "技能不存在")


async def _require_tools(session: AsyncSession, tool_ids: list[UUID]) -> None:
    repos = get_repositories(session)
    for tool_id in tool_ids:
        if await repos.agent.tool.get(tool_id) is None:
            raise http_error(400, "tool_not_found", "工具不存在")


async def _require_mcp(session: AsyncSession, server_id: UUID | None, *, required: bool) -> None:
    if server_id is None:
        if required:
            raise http_error(400, "mcp_server_required", "mcp 工具必须绑定 MCP Server")
        return
    repos = get_repositories(session)
    if await repos.agent.mcp_server.get(server_id) is None:
        raise http_error(400, "mcp_server_not_found", "MCP Server 不存在")


async def _require_flow(session: AsyncSession, flow_id: UUID) -> None:
    repos = get_repositories(session)
    if await repos.agent.flow.get(flow_id) is None:
        raise http_error(400, "flow_not_found", "工作流不存在")


async def _require_profile(session: AsyncSession, profile_id: UUID) -> None:
    repos = get_repositories(session)
    if await repos.agent.profile.get(profile_id) is None:
        raise http_error(400, "profile_not_found", "规划配置不存在")


def _valid_cron(cron: str) -> None:
    if not croniter.is_valid(cron):
        raise http_error(400, "cron_invalid", "cron 表达式非法")


def _profile_out(row: AgentProfile) -> ProfileOut:
    return ProfileOut(
        id=row.id,
        code=row.code,
        name=row.name,
        system_prompt=row.system_prompt,
        default_llm_id=row.default_llm_id,
        skill_ids=_uuids_from_json(list(row.skill_ids)),
    )


def _skill_out(row: AgentSkill) -> SkillOut:
    return SkillOut(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        tool_ids=_uuids_from_json(list(row.tool_ids)),
        prompt_template=row.prompt_template,
    )


def _tool_out(row: AgentTool) -> ToolOut:
    return ToolOut(
        id=row.id,
        code=row.code,
        name=row.name,
        kind=row.kind,
        parameter_schema=dict(row.schema_),
        config=dict(row.config),
        mcp_server_id=row.mcp_server_id,
    )


def _mcp_out(row: AgentMcpServer) -> McpOut:
    return McpOut(
        id=row.id,
        code=row.code,
        name=row.name,
        transport=row.transport,
        config=dict(row.config),
        is_active=row.is_active,
    )


def _beat_out(row: AgentBeatTask) -> BeatOut:
    return BeatOut(
        id=row.id,
        code=row.code,
        flow_id=row.flow_id,
        profile_id=row.profile_id,
        cron=row.cron,
        input_payload=dict(row.input_payload),
        is_enabled=row.is_enabled,
        last_triggered_at=row.last_triggered_at,
    )


async def _put_bindings(
    session: AsyncSession,
    resource_type: str,
    resource_id: UUID,
    body: BindingPutBody,
) -> list[BindingItem]:
    from api.apps.agent_config.access import parse_resource_type

    typed = parse_resource_type(resource_type)
    return await save_bindings(session, typed, resource_id, body.bindings)


# --- Profile ---


@router.get("/profiles", response_model=list[ProfileOut])
async def list_profiles(
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ProfileOut]:
    rows = await load_visible_profile_rows(session, current.id, offset=offset, limit=limit)
    return [_profile_out(row) for row in rows]


@router.post("/profiles", response_model=ProfileOut)
async def create_profile(
    body: ProfileCreateBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> ProfileOut:
    await _require_llm(session, body.default_llm_id)
    await _require_skills(session, body.skill_ids)
    repos = get_repositories(session)
    row = AgentProfile(
        code=await repos.agent.allocate_code("profile"),
        name=body.name,
        system_prompt=body.system_prompt,
        default_llm_id=body.default_llm_id,
        skill_ids=_uuid_strs(body.skill_ids),
        owner_organization_id=None,
    )
    try:
        await repos.agent.profile.add(row)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "profile_code_conflict", "Profile code 已存在") from exc
    await upsert_config_asset(session, asset_type="profile", resource_id=row.id, name=row.name)
    logger.info("创建 Profile id={} code={}", row.id, row.code)
    return _profile_out(row)


@router.get("/profiles/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: UUID,
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
) -> ProfileOut:
    await assert_config_visible(
        session,
        current.id,
        "profile",
        profile_id,
        missing_code="profile_not_found",
        missing_message="Profile 不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.profile.get(profile_id)
    if row is None:
        raise http_error(404, "profile_not_found", "Profile 不存在")
    return _profile_out(row)


@router.patch("/profiles/{profile_id}", response_model=ProfileOut)
async def patch_profile(
    profile_id: UUID,
    body: ProfilePatchBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> ProfileOut:
    repos = get_repositories(session)
    row = await repos.agent.profile.get(profile_id)
    if row is None:
        raise http_error(404, "profile_not_found", "Profile 不存在")
    if body.default_llm_id is not None:
        await _require_llm(session, body.default_llm_id)
        row.default_llm_id = body.default_llm_id
    if body.skill_ids is not None:
        await _require_skills(session, body.skill_ids)
        row.skill_ids = _uuid_strs(body.skill_ids)
    if body.name is not None:
        row.name = body.name
    if body.system_prompt is not None:
        row.system_prompt = body.system_prompt
    await upsert_config_asset(session, asset_type="profile", resource_id=row.id, name=row.name)
    return _profile_out(row)


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await assert_config_visible(
        session,
        current.id,
        "profile",
        profile_id,
        missing_code="profile_not_found",
        missing_message="Profile 不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.profile.get(profile_id)
    if row is None:
        raise http_error(404, "profile_not_found", "Profile 不存在")
    if await repos.agent.count_beats_for_profile(profile_id) > 0:
        raise http_error(409, "profile_in_use", "Profile 仍被定时任务引用，不可删除")
    if await repos.conversation.count_active_by_profile(profile_id) > 0:
        raise http_error(409, "profile_in_use", "Profile 仍被未删除会话引用，不可删除")
    await drop_config_resource(session, "profile", profile_id)
    await session.delete(row)
    logger.info("删除 Profile id={}", profile_id)
    return {"status": "deleted"}


@router.get("/profiles/{profile_id}/bindings", response_model=list[BindingItem])
async def get_profile_bindings(
    profile_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.profile.get(profile_id) is None:
        raise http_error(404, "profile_not_found", "Profile 不存在")
    return await load_bindings(session, "profile", profile_id)


@router.put("/profiles/{profile_id}/bindings", response_model=list[BindingItem])
async def put_profile_bindings(
    profile_id: UUID,
    body: BindingPutBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.profile.get(profile_id) is None:
        raise http_error(404, "profile_not_found", "Profile 不存在")
    return await _put_bindings(session, "profile", profile_id, body)


# --- Skill ---


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[SkillOut]:
    rows = await load_visible_skill_rows(session, current.id, offset=offset, limit=limit)
    return [_skill_out(row) for row in rows]


@router.post("/skills", response_model=SkillOut)
async def create_skill(
    body: SkillCreateBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> SkillOut:
    await _require_tools(session, body.tool_ids)
    repos = get_repositories(session)
    row = AgentSkill(
        code=await repos.agent.allocate_code("skill"),
        name=body.name,
        description=body.description,
        tool_ids=_uuid_strs(body.tool_ids),
        prompt_template=body.prompt_template,
    )
    try:
        await repos.agent.skill.add(row)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "skill_code_conflict", "Skill code 已存在") from exc
    await upsert_config_asset(session, asset_type="skill", resource_id=row.id, name=row.name)
    logger.info("创建 Skill id={} code={}", row.id, row.code)
    return _skill_out(row)


@router.get("/skills/{skill_id}", response_model=SkillOut)
async def get_skill(
    skill_id: UUID,
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
) -> SkillOut:
    await assert_config_visible(
        session,
        current.id,
        "skill",
        skill_id,
        missing_code="skill_not_found",
        missing_message="技能不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.skill.get(skill_id)
    if row is None:
        raise http_error(404, "skill_not_found", "技能不存在")
    return _skill_out(row)


@router.patch("/skills/{skill_id}", response_model=SkillOut)
async def patch_skill(
    skill_id: UUID,
    body: SkillPatchBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> SkillOut:
    repos = get_repositories(session)
    row = await repos.agent.skill.get(skill_id)
    if row is None:
        raise http_error(404, "skill_not_found", "技能不存在")
    if body.tool_ids is not None:
        await _require_tools(session, body.tool_ids)
        row.tool_ids = _uuid_strs(body.tool_ids)
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.prompt_template is not None:
        row.prompt_template = body.prompt_template
    await upsert_config_asset(session, asset_type="skill", resource_id=row.id, name=row.name)
    return _skill_out(row)


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await assert_config_visible(
        session,
        current.id,
        "skill",
        skill_id,
        missing_code="skill_not_found",
        missing_message="技能不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.skill.get(skill_id)
    if row is None:
        raise http_error(404, "skill_not_found", "技能不存在")
    if await repos.agent.skill_id_in_use(skill_id):
        raise http_error(409, "skill_in_use", "技能仍被 Profile 引用，不可删除")
    await drop_config_resource(session, "skill", skill_id)
    await session.delete(row)
    logger.info("删除 Skill id={}", skill_id)
    return {"status": "deleted"}


@router.get("/skills/{skill_id}/bindings", response_model=list[BindingItem])
async def get_skill_bindings(
    skill_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.skill.get(skill_id) is None:
        raise http_error(404, "skill_not_found", "技能不存在")
    return await load_bindings(session, "skill", skill_id)


@router.put("/skills/{skill_id}/bindings", response_model=list[BindingItem])
async def put_skill_bindings(
    skill_id: UUID,
    body: BindingPutBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.skill.get(skill_id) is None:
        raise http_error(404, "skill_not_found", "技能不存在")
    return await _put_bindings(session, "skill", skill_id, body)


# --- Tool ---


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ToolOut]:
    rows = await load_visible_tool_rows(session, current.id, offset=offset, limit=limit)
    return [_tool_out(row) for row in rows]


@router.post("/tools", response_model=ToolOut)
async def create_tool(
    body: ToolCreateBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> ToolOut:
    await _require_mcp(session, body.mcp_server_id, required=body.kind == "mcp")
    repos = get_repositories(session)
    row = AgentTool(
        code=await repos.agent.allocate_code("tool"),
        name=body.name,
        kind=body.kind,
        schema_=dict(body.parameter_schema),
        config=dict(body.config),
        mcp_server_id=body.mcp_server_id,
    )
    try:
        await repos.agent.tool.add(row)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "tool_code_conflict", "Tool code 已存在") from exc
    await upsert_config_asset(session, asset_type="tool", resource_id=row.id, name=row.name)
    logger.info("创建 Tool id={} code={}", row.id, row.code)
    return _tool_out(row)


@router.get("/tools/{tool_id}", response_model=ToolOut)
async def get_tool(
    tool_id: UUID,
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
) -> ToolOut:
    await assert_config_visible(
        session,
        current.id,
        "tool",
        tool_id,
        missing_code="tool_not_found",
        missing_message="工具不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.tool.get(tool_id)
    if row is None:
        raise http_error(404, "tool_not_found", "工具不存在")
    return _tool_out(row)


@router.patch("/tools/{tool_id}", response_model=ToolOut)
async def patch_tool(
    tool_id: UUID,
    body: ToolPatchBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> ToolOut:
    repos = get_repositories(session)
    row = await repos.agent.tool.get(tool_id)
    if row is None:
        raise http_error(404, "tool_not_found", "工具不存在")
    kind = body.kind if body.kind is not None else row.kind
    mcp_id = body.mcp_server_id if body.mcp_server_id is not None else row.mcp_server_id
    await _require_mcp(session, mcp_id, required=kind == "mcp")
    if body.kind is not None:
        row.kind = body.kind
    if body.mcp_server_id is not None:
        row.mcp_server_id = body.mcp_server_id
    if body.name is not None:
        row.name = body.name
    if body.parameter_schema is not None:
        row.schema_ = dict(body.parameter_schema)
    if body.config is not None:
        row.config = dict(body.config)
    await upsert_config_asset(session, asset_type="tool", resource_id=row.id, name=row.name)
    return _tool_out(row)


@router.delete("/tools/{tool_id}")
async def delete_tool(
    tool_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await assert_config_visible(
        session,
        current.id,
        "tool",
        tool_id,
        missing_code="tool_not_found",
        missing_message="工具不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.tool.get(tool_id)
    if row is None:
        raise http_error(404, "tool_not_found", "工具不存在")
    if await repos.agent.tool_id_in_use(tool_id):
        raise http_error(409, "tool_in_use", "工具仍被 Skill 引用，不可删除")
    await drop_config_resource(session, "tool", tool_id)
    await session.delete(row)
    logger.info("删除 Tool id={}", tool_id)
    return {"status": "deleted"}


@router.get("/tools/{tool_id}/bindings", response_model=list[BindingItem])
async def get_tool_bindings(
    tool_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.tool.get(tool_id) is None:
        raise http_error(404, "tool_not_found", "工具不存在")
    return await load_bindings(session, "tool", tool_id)


@router.put("/tools/{tool_id}/bindings", response_model=list[BindingItem])
async def put_tool_bindings(
    tool_id: UUID,
    body: BindingPutBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.tool.get(tool_id) is None:
        raise http_error(404, "tool_not_found", "工具不存在")
    return await _put_bindings(session, "tool", tool_id, body)


# --- MCP ---


@router.get("/mcp-servers", response_model=list[McpOut])
async def list_mcp(
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[McpOut]:
    rows = await load_visible_mcp_rows(session, current.id, offset=offset, limit=limit)
    return [_mcp_out(row) for row in rows]


@router.post("/mcp-servers", response_model=McpOut)
async def create_mcp(
    body: McpCreateBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> McpOut:
    repos = get_repositories(session)
    row = AgentMcpServer(
        code=await repos.agent.allocate_code("mcp"),
        name=body.name,
        transport=body.transport,
        config=dict(body.config),
        is_active=body.is_active,
    )
    try:
        await repos.agent.mcp_server.add(row)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "mcp_code_conflict", "MCP code 已存在") from exc
    await upsert_config_asset(session, asset_type="mcp_server", resource_id=row.id, name=row.name)
    logger.info("创建 MCP Server id={} code={}", row.id, row.code)
    return _mcp_out(row)


@router.get("/mcp-servers/{server_id}", response_model=McpOut)
async def get_mcp(
    server_id: UUID,
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
) -> McpOut:
    await assert_config_visible(
        session,
        current.id,
        "mcp_server",
        server_id,
        missing_code="mcp_server_not_found",
        missing_message="MCP Server 不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.mcp_server.get(server_id)
    if row is None:
        raise http_error(404, "mcp_server_not_found", "MCP Server 不存在")
    return _mcp_out(row)


@router.patch("/mcp-servers/{server_id}", response_model=McpOut)
async def patch_mcp(
    server_id: UUID,
    body: McpPatchBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> McpOut:
    repos = get_repositories(session)
    row = await repos.agent.mcp_server.get(server_id)
    if row is None:
        raise http_error(404, "mcp_server_not_found", "MCP Server 不存在")
    if body.name is not None:
        row.name = body.name
    if body.transport is not None:
        row.transport = body.transport
    if body.config is not None:
        row.config = dict(body.config)
    if body.is_active is not None:
        row.is_active = body.is_active
    await upsert_config_asset(session, asset_type="mcp_server", resource_id=row.id, name=row.name)
    return _mcp_out(row)


@router.delete("/mcp-servers/{server_id}")
async def delete_mcp(
    server_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await assert_config_visible(
        session,
        current.id,
        "mcp_server",
        server_id,
        missing_code="mcp_server_not_found",
        missing_message="MCP Server 不存在",
    )
    repos = get_repositories(session)
    row = await repos.agent.mcp_server.get(server_id)
    if row is None:
        raise http_error(404, "mcp_server_not_found", "MCP Server 不存在")
    if await repos.agent.count_tools_for_mcp(server_id) > 0:
        raise http_error(409, "mcp_server_in_use", "MCP Server 仍被工具引用，不可删除")
    await drop_config_resource(session, "mcp_server", server_id)
    await session.delete(row)
    logger.info("删除 MCP Server id={}", server_id)
    return {"status": "deleted"}


@router.get("/mcp-servers/{server_id}/bindings", response_model=list[BindingItem])
async def get_mcp_bindings(
    server_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.mcp_server.get(server_id) is None:
        raise http_error(404, "mcp_server_not_found", "MCP Server 不存在")
    return await load_bindings(session, "mcp_server", server_id)


@router.put("/mcp-servers/{server_id}/bindings", response_model=list[BindingItem])
async def put_mcp_bindings(
    server_id: UUID,
    body: BindingPutBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    repos = get_repositories(session)
    if await repos.agent.mcp_server.get(server_id) is None:
        raise http_error(404, "mcp_server_not_found", "MCP Server 不存在")
    return await _put_bindings(session, "mcp_server", server_id, body)


# --- Beat（工作流或规划，恰一绑定）---


@router.get("/beat-tasks", response_model=list[BeatOut])
async def list_beats(
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[BeatOut]:
    repos = get_repositories(session)
    rows = await repos.agent.beat_task.list(offset=offset, limit=min(limit, 100))
    return [_beat_out(row) for row in rows]


@router.post("/beat-tasks", response_model=BeatOut)
async def create_beat(
    body: BeatCreateBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> BeatOut:
    _valid_cron(body.cron)
    if body.flow_id is not None and body.profile_id is not None:
        raise http_error(400, "beat_target_conflict", "flow_id 与 profile_id 只能填一个")
    if body.flow_id is None and body.profile_id is None:
        raise http_error(400, "beat_target_required", "需要 flow_id 或 profile_id")
    if body.flow_id is not None:
        await _require_flow(session, body.flow_id)
    if body.profile_id is not None:
        await _require_profile(session, body.profile_id)
    repos = get_repositories(session)
    row = AgentBeatTask(
        code=await repos.agent.allocate_code("beat"),
        flow_id=body.flow_id,
        profile_id=body.profile_id,
        cron=body.cron,
        input_payload=dict(body.input_payload),
        is_enabled=body.is_enabled,
    )
    try:
        await repos.agent.beat_task.add(row)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "beat_code_conflict", "Beat code 已存在") from exc
    logger.info(
        "创建 Beat id={} code={} flow_id={} profile_id={}",
        row.id,
        row.code,
        row.flow_id,
        row.profile_id,
    )
    return _beat_out(row)


@router.get("/beat-tasks/{task_id}", response_model=BeatOut)
async def get_beat(
    task_id: UUID,
    current: CurrentUser = Depends(_use_agent_config),
    session: AsyncSession = Depends(db_session),
) -> BeatOut:
    repos = get_repositories(session)
    row = await repos.agent.beat_task.get(task_id)
    if row is None:
        raise http_error(404, "beat_not_found", "定时任务不存在")
    return _beat_out(row)


@router.patch("/beat-tasks/{task_id}", response_model=BeatOut)
async def patch_beat(
    task_id: UUID,
    body: BeatPatchBody,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> BeatOut:
    repos = get_repositories(session)
    row = await repos.agent.beat_task.get(task_id)
    if row is None:
        raise http_error(404, "beat_not_found", "定时任务不存在")
    if body.cron is not None:
        _valid_cron(body.cron)
        row.cron = body.cron
    if body.input_payload is not None:
        row.input_payload = dict(body.input_payload)
    return _beat_out(row)


@router.post("/beat-tasks/{task_id}/enable", response_model=BeatOut)
async def enable_beat(
    task_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> BeatOut:
    repos = get_repositories(session)
    row = await repos.agent.beat_task.get(task_id)
    if row is None:
        raise http_error(404, "beat_not_found", "定时任务不存在")
    row.is_enabled = True
    return _beat_out(row)


@router.post("/beat-tasks/{task_id}/disable", response_model=BeatOut)
async def disable_beat(
    task_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> BeatOut:
    repos = get_repositories(session)
    row = await repos.agent.beat_task.get(task_id)
    if row is None:
        raise http_error(404, "beat_not_found", "定时任务不存在")
    row.is_enabled = False
    return _beat_out(row)


@router.delete("/beat-tasks/{task_id}")
async def delete_beat(
    task_id: UUID,
    current: CurrentUser = Depends(_ctrl_agent_config),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    _ = current
    repos = get_repositories(session)
    row = await repos.agent.beat_task.get(task_id)
    if row is None:
        raise http_error(404, "beat_not_found", "定时任务不存在")
    await session.delete(row)
    logger.info("删除 Beat id={}", task_id)
    return {"status": "deleted"}
