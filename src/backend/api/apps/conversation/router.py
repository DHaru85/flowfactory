"""会话 REST 与 SSE。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.apps.conversation.schemas import (
    ConversationCreateBody,
    ConversationOut,
    MessageOut,
    SendMessageBody,
    SendMessageOut,
)
from api.deps import (
    CurrentUser,
    db_session,
    get_current_user,
    get_current_user_detached,
    get_workflow_runtime,
)
from api.errors import http_error
from api.sse.bus import get_sse_bus
from api.sse.protocol import run_submitted_event
from api.sse.stream import conversation_sse_iter
from data_schema.conversation.models import Conversation, Message
from service.database.session import session_scope
from service.persistence.factory import get_repositories
from service.runtime.schemas import RunStatePayload, StartRunRequest
from service.runtime.service import WorkflowRuntimeService

router = APIRouter(prefix="/api/v1/conversations", tags=["conversation"])


def _to_conv_out(row: Conversation) -> ConversationOut:
    return ConversationOut(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        app_key=row.app_key,
        flow_id=row.flow_id,
        status=row.status,
    )


def _to_msg_out(row: Message) -> MessageOut:
    return MessageOut(
        id=row.id,
        conversation_id=row.conversation_id,
        role=row.role,
        content_blocks=list(row.content_blocks),
        status=row.status,
    )


async def _owned_conversation(
    session: AsyncSession,
    current: CurrentUser,
    conversation_id: UUID,
) -> Conversation:
    repos = get_repositories(session)
    conv = await repos.conversation.conversation.get(conversation_id)
    if conv is None or conv.status == "deleted":
        raise http_error(404, "conversation_not_found", "会话不存在")
    if conv.user_id != current.id:
        raise http_error(403, "conversation_forbidden", "无权访问该会话")
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ConversationOut]:
    repos = get_repositories(session)
    rows = await repos.conversation.list_by_user(current.id, offset=offset, limit=min(limit, 100))
    return [_to_conv_out(row) for row in rows]


@router.post("", response_model=ConversationOut)
async def create_conversation(
    body: ConversationCreateBody,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> ConversationOut:
    repos = get_repositories(session)
    conv = Conversation(
        user_id=current.id,
        title=body.title,
        app_key="conversation",
        flow_id=body.flow_id,
        status="active",
        metadata_=body.metadata or {},
    )
    await repos.conversation.conversation.add(conv)
    return _to_conv_out(conv)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> ConversationOut:
    conv = await _owned_conversation(session, current, conversation_id)
    return _to_conv_out(conv)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 100,
) -> list[MessageOut]:
    await _owned_conversation(session, current, conversation_id)
    repos = get_repositories(session)
    rows = await repos.conversation.list_messages(
        conversation_id, offset=offset, limit=min(limit, 200)
    )
    return [_to_msg_out(row) for row in rows]


@router.post("/messages", response_model=SendMessageOut)
async def send_message(
    body: SendMessageBody,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    runtime: WorkflowRuntimeService = Depends(get_workflow_runtime),
) -> SendMessageOut:
    repos = get_repositories(session)
    if body.conversation_id is None:
        title = body.content[:64]
        conv = Conversation(
            user_id=current.id,
            title=title,
            app_key=body.app_key,
            flow_id=body.flow_id,
            status="active",
            metadata_=body.metadata or {},
        )
        await repos.conversation.conversation.add(conv)
    else:
        conv = await _owned_conversation(session, current, body.conversation_id)
        if body.flow_id is not None:
            conv.flow_id = body.flow_id
        if body.metadata:
            conv.metadata_ = {**dict(conv.metadata_), **body.metadata}

    flow_id = body.flow_id or conv.flow_id
    if flow_id is None:
        raise http_error(400, "flow_id_required", "发消息需要 flow_id")

    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content_blocks=[{"type": "text", "text": body.content}],
        status="completed",
    )
    await repos.conversation.message.add(user_msg)
    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content_blocks=[],
        status="streaming",
    )
    await repos.conversation.message.add(assistant_msg)

    run_id = await runtime.start(
        StartRunRequest(
            user_id=current.id,
            flow_id=flow_id,
            conversation_id=conv.id,
            input_payload=RunStatePayload(
                messages=[{"role": "user", "content": body.content}],
                variables={"input": body.content},
                metadata={"app_key": conv.app_key, "assistant_message_id": str(assistant_msg.id)},
            ),
        )
    )
    event = run_submitted_event(run_id=run_id, message_id=assistant_msg.id)
    await get_sse_bus().publish(conv.id, event)
    return SendMessageOut(
        conversation_id=conv.id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
        run_id=run_id,
    )


@router.get("/{conversation_id}/events")
async def subscribe_events(
    conversation_id: UUID,
    current: CurrentUser = Depends(get_current_user_detached),
) -> StreamingResponse:
    async with session_scope() as session:
        await _owned_conversation(session, current, conversation_id)
    return StreamingResponse(
        conversation_sse_iter(conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
