"""软删数据空闲清理。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.agent.models import AgentBeatTask, AgentCheckpointSchema, AgentFlow
from data_schema.conversation.models import Conversation, Message
from data_schema.workflow.models import RunSnapshot
from settings.config import get_settings


async def purge_expired_soft_deleted(session: AsyncSession) -> dict[str, int]:
    """物理删除超过保留期且无引用的软删会话与工作流。"""
    cfg = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=max(1, cfg.soft_delete_retention_days))
    conv_ids = list(
        (
            await session.scalars(
                select(Conversation.id).where(
                    Conversation.status == "deleted",
                    Conversation.updated_at < cutoff,
                )
            )
        ).all()
    )
    messages = 0
    conversations = 0
    if conv_ids:
        msg_result = await session.execute(
            delete(Message).where(Message.conversation_id.in_(conv_ids))
        )
        messages = int(msg_result.rowcount or 0)
        conv_result = await session.execute(
            delete(Conversation).where(Conversation.id.in_(conv_ids))
        )
        conversations = int(conv_result.rowcount or 0)

    flow_rows = list(
        (
            await session.scalars(
                select(AgentFlow).where(
                    AgentFlow.status == "deleted",
                    AgentFlow.updated_at < cutoff,
                )
            )
        ).all()
    )
    flows = 0
    for flow in flow_rows:
        beat = await session.scalar(
            select(AgentBeatTask.id).where(AgentBeatTask.flow_id == flow.id).limit(1)
        )
        if beat is not None:
            continue
        conv = await session.scalar(
            select(Conversation.id).where(Conversation.flow_id == flow.id).limit(1)
        )
        if conv is not None:
            continue
        run = await session.scalar(
            select(RunSnapshot.id).where(RunSnapshot.flow_id == flow.id).limit(1)
        )
        if run is not None:
            continue
        await session.execute(
            delete(AgentCheckpointSchema).where(AgentCheckpointSchema.flow_id == flow.id)
        )
        await session.delete(flow)
        flows += 1

    logger.info(
        "软删清理 conversations={} messages={} flows={}",
        conversations,
        messages,
        flows,
    )
    return {
        "conversations": conversations,
        "messages": messages,
        "flows": flows,
    }
