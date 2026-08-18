"""Conversation 域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.conversation.models import Conversation, Message
from service.persistence.base import Repository


class ConversationRepository:
    """会话与消息聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.conversation = Repository(session, Conversation)
        self.message = Repository(session, Message)

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.status != "deleted")
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_streaming_message(self, conversation_id: uuid.UUID) -> Message | None:
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.status == "streaming",
        )
        return await self._session.scalar(stmt)
