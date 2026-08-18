"""外层编排协议。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from service.runtime.schemas import HitlResumeInput, HitlResumeOutput, StartRunRequest


class OuterOrchestrator(ABC):
    """图外编排：不复制 LangGraph checkpoint。"""

    @abstractmethod
    async def start_run(self, request: StartRunRequest) -> UUID:
        raise NotImplementedError

    @abstractmethod
    async def resume_run(self, hitl: HitlResumeInput) -> HitlResumeOutput:
        raise NotImplementedError

    @abstractmethod
    async def cancel_run(self, run_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def signal_hitl(self, hitl: HitlResumeInput) -> None:
        raise NotImplementedError
