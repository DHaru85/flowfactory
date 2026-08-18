"""仓储基类。"""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    """通用 CRUD 仓储（异步）。"""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self.model = model

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self._session.get(self.model, entity_id)

    async def list(self, *, offset: int = 0, limit: int = 50) -> list[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        self._session.delete(entity)
        await self._session.flush()
