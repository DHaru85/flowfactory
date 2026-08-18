"""Observability 域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.observability.models import (
    ObsLlmCall,
    ObsPromptSnapshot,
    ObsSpan,
    ObsToolInvocation,
    ObsTrace,
)
from service.persistence.base import Repository


class ObservabilityRepository:
    """可观测性聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.trace = Repository(session, ObsTrace)
        self.span = Repository(session, ObsSpan)
        self.llm_call = Repository(session, ObsLlmCall)
        self.tool_invocation = Repository(session, ObsToolInvocation)
        self.prompt_snapshot = Repository(session, ObsPromptSnapshot)

    async def get_trace_by_otel_id(self, trace_id: str) -> ObsTrace | None:
        stmt = select(ObsTrace).where(ObsTrace.trace_id == trace_id)
        return await self._session.scalar(stmt)

    async def list_spans_by_trace(self, trace_id: str) -> list[ObsSpan]:
        stmt = select(ObsSpan).where(ObsSpan.trace_id == trace_id)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_llm_calls_by_run(self, run_id: uuid.UUID) -> list[ObsLlmCall]:
        stmt = select(ObsLlmCall).where(ObsLlmCall.run_id == run_id)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def add_prompt_snapshots(self, snapshots: list[ObsPromptSnapshot]) -> None:
        self._session.add_all(snapshots)
        await self._session.flush()
