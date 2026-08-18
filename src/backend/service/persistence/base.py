"""仓储基类。"""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_schema.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    """通用 CRUD 仓储。"""

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self._session = session
        self.model = model

    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return self._session.get(self.model, entity_id)

    def list(self, *, offset: int = 0, limit: int = 50) -> list[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        return list(self._session.scalars(stmt).all())

    def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        self._session.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        self._session.delete(entity)
        self._session.flush()
