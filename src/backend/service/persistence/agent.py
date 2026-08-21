"""Agent 配置域仓储。"""

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.agent.models import (
    AgentBeatTask,
    AgentCheckpointSchema,
    AgentFlow,
    AgentLlm,
    AgentMcpServer,
    AgentProfile,
    AgentResourceBinding,
    AgentSkill,
    AgentTool,
)
from service.persistence.base import Repository


class AgentConfigRepository:
    """Agent 配置聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.llm = Repository(session, AgentLlm)
        self.profile = Repository(session, AgentProfile)
        self.skill = Repository(session, AgentSkill)
        self.tool = Repository(session, AgentTool)
        self.mcp_server = Repository(session, AgentMcpServer)
        self.beat_task = Repository(session, AgentBeatTask)
        self.flow = Repository(session, AgentFlow)
        self.binding = Repository(session, AgentResourceBinding)

    async def get_flow_by_code_version(
        self,
        code: str,
        version: int,
    ) -> AgentFlow | None:
        stmt = select(AgentFlow).where(
            AgentFlow.code == code,
            AgentFlow.version == version,
        )
        return await self._session.scalar(stmt)

    async def get_latest_published_flow(self, code: str) -> AgentFlow | None:
        stmt = (
            select(AgentFlow)
            .where(AgentFlow.code == code, AgentFlow.status == "published")
            .order_by(AgentFlow.version.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def add_flow(self, flow: AgentFlow) -> AgentFlow:
        self._session.add(flow)
        await self._session.flush()
        return flow

    async def get_tool_by_code(self, code: str) -> AgentTool | None:
        stmt = select(AgentTool).where(AgentTool.code == code)
        return await self._session.scalar(stmt)

    async def get_mcp_server(self, server_id: uuid.UUID) -> AgentMcpServer | None:
        return await self._session.get(AgentMcpServer, server_id)

    async def get_llm_by_code(self, code: str) -> AgentLlm | None:
        stmt = select(AgentLlm).where(AgentLlm.code == code)
        return await self._session.scalar(stmt)

    async def list_llms(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        is_active: bool | None = None,
    ) -> list[AgentLlm]:
        stmt = select(AgentLlm)
        if is_active is not None:
            stmt = stmt.where(AgentLlm.is_active.is_(is_active))
        stmt = stmt.order_by(AgentLlm.updated_at.desc()).offset(offset).limit(limit)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_profile_by_code(self, code: str) -> AgentProfile | None:
        stmt = select(AgentProfile).where(AgentProfile.code == code)
        return await self._session.scalar(stmt)

    async def get_skill_by_code(self, code: str) -> AgentSkill | None:
        stmt = select(AgentSkill).where(AgentSkill.code == code)
        return await self._session.scalar(stmt)

    async def list_bindings(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> list[AgentResourceBinding]:
        stmt = select(AgentResourceBinding).where(
            AgentResourceBinding.resource_type == resource_type,
            AgentResourceBinding.resource_id == resource_id,
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_bindings_for_subjects(
        self,
        resource_type: str,
        subjects: Sequence[tuple[str, uuid.UUID]],
    ) -> list[AgentResourceBinding]:
        if not subjects:
            return []
        conditions = [
            and_(
                AgentResourceBinding.subject_type == subject_type,
                AgentResourceBinding.subject_id == subject_id,
            )
            for subject_type, subject_id in subjects
        ]
        stmt = select(AgentResourceBinding).where(
            AgentResourceBinding.resource_type == resource_type,
            or_(*conditions),
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_bindings_for_resource_subjects(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
        subjects: Sequence[tuple[str, uuid.UUID]],
    ) -> list[AgentResourceBinding]:
        if not subjects:
            return []
        conditions = [
            and_(
                AgentResourceBinding.subject_type == subject_type,
                AgentResourceBinding.subject_id == subject_id,
            )
            for subject_type, subject_id in subjects
        ]
        stmt = select(AgentResourceBinding).where(
            AgentResourceBinding.resource_type == resource_type,
            AgentResourceBinding.resource_id == resource_id,
            or_(*conditions),
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def replace_bindings(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
        rows: list[AgentResourceBinding],
    ) -> list[AgentResourceBinding]:
        await self._session.execute(
            delete(AgentResourceBinding).where(
                AgentResourceBinding.resource_type == resource_type,
                AgentResourceBinding.resource_id == resource_id,
            )
        )
        for row in rows:
            self._session.add(row)
        await self._session.flush()
        return rows

    async def list_enabled_beat_tasks(self) -> list[AgentBeatTask]:
        stmt = select(AgentBeatTask).where(AgentBeatTask.is_enabled.is_(True))
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_flows(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
        code: str | None = None,
    ) -> list[AgentFlow]:
        stmt = select(AgentFlow).where(AgentFlow.status != "deleted")
        if status is not None:
            stmt = stmt.where(AgentFlow.status == status)
        if code is not None:
            stmt = stmt.where(AgentFlow.code == code)
        stmt = stmt.order_by(AgentFlow.updated_at.desc()).offset(offset).limit(limit)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_published_flow_summaries(self) -> list[tuple[str, int]]:
        """每个 code 取已发布的最大 version。"""
        stmt = (
            select(AgentFlow.code, AgentFlow.version)
            .where(AgentFlow.status == "published")
            .order_by(AgentFlow.code, AgentFlow.version.desc())
        )
        rows = (await self._session.execute(stmt)).all()
        latest: dict[str, int] = {}
        for code, version in rows:
            if code not in latest:
                latest[code] = int(version)
        return [(code, ver) for code, ver in latest.items()]

    async def archive_published_siblings(self, code: str, except_id: uuid.UUID) -> None:
        stmt = select(AgentFlow).where(
            AgentFlow.code == code,
            AgentFlow.status == "published",
            AgentFlow.id != except_id,
        )
        result = await self._session.scalars(stmt)
        for row in result.all():
            row.status = "archived"

    async def count_profiles_for_llm(self, llm_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(AgentProfile).where(
            AgentProfile.default_llm_id == llm_id
        )
        return int(await self._session.scalar(stmt) or 0)

    async def count_flows_for_profile(self, profile_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(AgentFlow).where(
            AgentFlow.profile_id == profile_id,
            AgentFlow.status != "deleted",
        )
        return int(await self._session.scalar(stmt) or 0)

    async def drop_deleted_flows_for_profile(self, profile_id: uuid.UUID) -> None:
        """去掉已软删 Flow 对 Profile 的外键占用，以便硬删 Profile。"""
        stmt = select(AgentFlow).where(
            AgentFlow.profile_id == profile_id,
            AgentFlow.status == "deleted",
        )
        result = await self._session.scalars(stmt)
        for flow in result.all():
            await self._session.execute(
                delete(AgentCheckpointSchema).where(AgentCheckpointSchema.flow_id == flow.id)
            )
            await self._session.delete(flow)

    async def count_beats_for_profile(self, profile_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(AgentBeatTask).where(
            AgentBeatTask.profile_id == profile_id
        )
        return int(await self._session.scalar(stmt) or 0)

    async def count_beats_for_flow(self, flow_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(AgentBeatTask).where(
            AgentBeatTask.flow_id == flow_id
        )
        return int(await self._session.scalar(stmt) or 0)

    async def count_tools_for_mcp(self, server_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(AgentTool).where(
            AgentTool.mcp_server_id == server_id
        )
        return int(await self._session.scalar(stmt) or 0)

    async def skill_id_in_use(self, skill_id: uuid.UUID) -> bool:
        key = str(skill_id)
        rows = await self._session.scalars(select(AgentProfile.skill_ids))
        for raw in rows.all():
            if isinstance(raw, list) and key in {str(item) for item in raw}:
                return True
        return False

    async def tool_id_in_use(self, tool_id: uuid.UUID) -> bool:
        key = str(tool_id)
        rows = await self._session.scalars(select(AgentSkill.tool_ids))
        for raw in rows.all():
            if isinstance(raw, list) and key in {str(item) for item in raw}:
                return True
        return False
