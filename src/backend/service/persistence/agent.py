"""Agent 配置域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_schema.agent.models import (
    AgentBeatTask,
    AgentFlow,
    AgentLlm,
    AgentProfile,
    AgentTool,
)
from service.persistence.base import Repository


class AgentConfigRepository:
    """Agent 配置聚合仓储。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.llm = Repository(session, AgentLlm)
        self.profile = Repository(session, AgentProfile)
        self.tool = Repository(session, AgentTool)
        self.beat_task = Repository(session, AgentBeatTask)

    def get_flow_by_code_version(
        self,
        code: str,
        version: int,
    ) -> AgentFlow | None:
        stmt = select(AgentFlow).where(
            AgentFlow.code == code,
            AgentFlow.version == version,
        )
        return self._session.scalar(stmt)

    def get_latest_published_flow(self, code: str) -> AgentFlow | None:
        stmt = (
            select(AgentFlow)
            .where(AgentFlow.code == code, AgentFlow.status == "published")
            .order_by(AgentFlow.version.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def add_flow(self, flow: AgentFlow) -> AgentFlow:
        self._session.add(flow)
        self._session.flush()
        return flow

    def get_llm_by_code(self, code: str) -> AgentLlm | None:
        stmt = select(AgentLlm).where(AgentLlm.code == code)
        return self._session.scalar(stmt)

    def get_profile_by_code(self, code: str) -> AgentProfile | None:
        stmt = select(AgentProfile).where(AgentProfile.code == code)
        return self._session.scalar(stmt)

    def list_enabled_beat_tasks(self) -> list[AgentBeatTask]:
        stmt = select(AgentBeatTask).where(AgentBeatTask.is_enabled.is_(True))
        return list(self._session.scalars(stmt).all())

    def list_flows_by_profile(self, profile_id: uuid.UUID) -> list[AgentFlow]:
        stmt = select(AgentFlow).where(AgentFlow.profile_id == profile_id)
        return list(self._session.scalars(stmt).all())
