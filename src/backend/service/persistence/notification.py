"""Notification 域仓储。"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.notification.models import DeliveryLog, WebhookEndpoint
from service.persistence.base import Repository


class NotificationRepository:
    """Webhook 通知聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.endpoint = Repository(session, WebhookEndpoint)
        self.delivery_log = Repository(session, DeliveryLog)

    async def list_enabled_endpoints_for_event(self, event_type: str) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpoint).where(WebhookEndpoint.is_enabled.is_(True))
        result = await self._session.scalars(stmt)
        endpoints = list(result.all())
        return [ep for ep in endpoints if event_type in ep.event_types]

    async def list_retry_pending(self, before: datetime) -> list[DeliveryLog]:
        stmt = select(DeliveryLog).where(
            DeliveryLog.status == "failed",
            DeliveryLog.next_retry_at.is_not(None),
            DeliveryLog.next_retry_at <= before,
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def create_delivery(self, log: DeliveryLog) -> DeliveryLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
    ) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpoint).where(
            WebhookEndpoint.owner_organization_id == organization_id
        )
        result = await self._session.scalars(stmt)
        return list(result.all())
