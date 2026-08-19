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

    async def list_flows_by_profile(self, profile_id: uuid.UUID) -> list[AgentFlow]:
        stmt = select(AgentFlow).where(AgentFlow.profile_id == profile_id)
        result = await self._session.scalars(stmt)
        return list(result.all())
