"""Thread 可运行对象。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import ThreadSnapshot


class Thread:
    def __init__(self, snapshot: ThreadSnapshot, langgraph_thread_id: str) -> None:
        self.id = snapshot.id
        self.langgraph_thread_id = langgraph_thread_id
        self._snapshot = snapshot

    def bind_worker(self, worker_id: str) -> None:
        self._snapshot.worker_id = worker_id

    async def persist(self, session: AsyncSession) -> None:
        await session.flush()
