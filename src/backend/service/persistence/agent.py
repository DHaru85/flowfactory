"""Agent 配置域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.agent.models import (
    AgentBeatTask,
    AgentFlow,
    AgentLlm,
    AgentMcpServer,
    AgentProfile,
    AgentTool,
)
from service.persistence.base import Repository


class AgentConfigRepository:
    """Agent 配置聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.llm = Repository(session, AgentLlm)
        self.profile = Repository(session, AgentProfile)
        self.tool = Repository(session, AgentTool)
        self.mcp_server = Repository(session, AgentMcpServer)
        self.beat_task = Repository(session, AgentBeatTask)
        self.flow = Repository(session, AgentFlow)

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

    async def get_profile_by_code(self, code: str) -> AgentProfile | None:
        stmt = select(AgentProfile).where(AgentProfile.code == code)
        return await self._session.scalar(stmt)

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
        stmt = select(AgentFlow)
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

