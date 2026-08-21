"""会话 REST 与 SSE：planner / workflow 分路径，旧路径为 workflow 别名。"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.access import require_app, require_app_detached
from api.apps.conversation.schemas import (
    ConversationCreateBody,
    ConversationDetailOut,
    ConversationOut,
    HitlPendingOut,
    HitlResumeBody,
    HitlResumeOut,
    MessageOut,
    PlannerConversationCreateBody,
    PlannerSendMessageBody,
    SendMessageBody,
    SendMessageOut,
)
from api.deps import (
    CurrentUser,
    db_session,
    get_workflow_runtime,
)
from api.errors import http_error
from api.sse.stream import conversation_sse_iter
from data_schema.conversation.models import Conversation, Message
from data_schema.workflow.models import HitlPending, RunSnapshot
from service.auth.access import AccessControl
from service.database.session import session_scope
from service.persistence.factory import get_repositories
from service.runtime.constants import HITL_PENDING
from service.runtime.schemas import HitlResumeInput, RunStatePayload, StartRunRequest
from service.runtime.service import WorkflowRuntimeService

router = APIRouter(prefix="/api/v1/conversations", tags=["conversation"])

_use_conversation = require_app("conversation")
_ctrl_conversation = require_app("conversation", control=True)
_use_conversation_sse = require_app_detached("conversation")

APP_KEY_PLANNER = "planner"
APP_KEY_WORKFLOW = "workflow"
APP_KEY_CONVERSATION_LEGACY = "conversation"
WORKFLOW_APP_KEYS: tuple[str, ...] = (APP_KEY_WORKFLOW, APP_KEY_CONVERSATION_LEGACY)
PLANNER_APP_KEYS: tuple[str, ...] = (APP_KEY_PLANNER,)


def _to_conv_out(row: Conversation) -> ConversationOut:
    return ConversationOut(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        app_key=row.app_key,
        flow_id=row.flow_id,
        status=row.status,
    )


def _to_conv_detail(row: Conversation) -> ConversationDetailOut:
    return ConversationDetailOut(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        app_key=row.app_key,
        flow_id=row.flow_id,
        status=row.status,
        metadata=dict(row.metadata_),
    )


def _to_msg_out(row: Message) -> MessageOut:
    return MessageOut(
        id=row.id,
        conversation_id=row.conversation_id,
        role=row.role,
        content_blocks=list(row.content_blocks),
        status=row.status,
    )


def _hitl_form_schema(pending: HitlPending) -> dict[str, object] | None:
    stored = pending.resume_payload if isinstance(pending.resume_payload, dict) else None
    if stored is None:
        return None
    raw = stored.get("form_schema")
    if isinstance(raw, dict):
        return dict(raw)
    return None


def _to_hitl_out(pending: HitlPending, run: RunSnapshot) -> HitlPendingOut:
    return HitlPendingOut(
        id=pending.id,
        run_id=pending.run_id,
        conversation_id=run.conversation_id,
        node_id=pending.node_id,
        prompt=pending.prompt,
        form_schema=_hitl_form_schema(pending),
        status=pending.status,
        expires_at=pending.expires_at,
    )


async def _current_is_superuser(session: AsyncSession, current: CurrentUser) -> bool:
    repos = get_repositories(session)
    user = await repos.permission.user.get(current.id)
    return user is not None and user.is_superuser


async def _hitl_visible(
    session: AsyncSession,
    current: CurrentUser,
    hitl_id: UUID,
) -> tuple[HitlPending, RunSnapshot]:
    repos = get_repositories(session)
    pending = await repos.workflow.hitl.get(hitl_id)
    if pending is None:
        raise http_error(404, "hitl_not_found", "待办不存在")
    run = await repos.workflow.run.get(pending.run_id)
    if run is None:
        raise http_error(404, "hitl_not_found", "待办不存在")
    if await _current_is_superuser(session, current):
        return pending, run
    if run.user_id != current.id:
        raise http_error(404, "hitl_not_found", "待办不存在")
    if run.conversation_id is not None:
        conv = await repos.conversation.conversation.get(run.conversation_id)
        if conv is None or conv.user_id != current.id:
            raise http_error(404, "hitl_not_found", "待办不存在")
    return pending, run


def _sse_response(conversation_id: UUID) -> StreamingResponse:
    return StreamingResponse(
        conversation_sse_iter(conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _owned_conversation(
    session: AsyncSession,
    current: CurrentUser,
    conversation_id: UUID,
    allowed_app_keys: Sequence[str],
) -> Conversation:
    repos = get_repositories(session)
    conv = await repos.conversation.conversation.get(conversation_id)
    if conv is None or conv.status == "deleted":
        raise http_error(404, "conversation_not_found", "会话不存在")
    if conv.user_id != current.id:
        raise http_error(403, "conversation_forbidden", "无权访问该会话")
    if conv.app_key not in allowed_app_keys:
        raise http_error(404, "conversation_not_found", "会话不存在")
    return conv


async def _soft_delete_owned(
    session: AsyncSession,
    current: CurrentUser,
    conversation_id: UUID,
    allowed_app_keys: Sequence[str],
) -> None:
    conv = await _owned_conversation(session, current, conversation_id, allowed_app_keys)
    repos = get_repositories(session)
    await repos.conversation.soft_delete_conversation(conv.id)


async def _ensure_profile_usable(
    session: AsyncSession,
    current: CurrentUser,
    profile_id: UUID,
) -> None:
    repos = get_repositories(session)
    profile = await repos.agent.profile.get(profile_id)
    if profile is None:
        raise http_error(404, "profile_not_found", "规划配置不存在")
    access = AccessControl(session)
    if not await access.can_see_agent_resource(current.id, "profile", profile_id):
        raise http_error(404, "profile_not_found", "规划配置不存在")
    if profile.default_llm_id is None:
        return
    llm = await repos.agent.llm.get(profile.default_llm_id)
    if llm is None or not llm.is_active:
        raise http_error(400, "llm_inactive", "规划配置绑定的模型未启用或不存在")


def _metadata_profile_id(metadata: dict[str, object]) -> UUID | None:
    raw = metadata.get("profile_id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


async def _list_conversations(
    session: AsyncSession,
    current: CurrentUser,
    app_keys: Sequence[str],
    offset: int,
    limit: int,
) -> list[ConversationOut]:
    repos = get_repositories(session)
    rows = await repos.conversation.list_by_user(
        current.id,
        offset=offset,
        limit=min(limit, 100),
        app_keys=app_keys,
    )
    return [_to_conv_out(row) for row in rows]


async def _list_messages(
    session: AsyncSession,
    current: CurrentUser,
    conversation_id: UUID,
    allowed_app_keys: Sequence[str],
    offset: int,
    limit: int,
) -> list[MessageOut]:
    await _owned_conversation(session, current, conversation_id, allowed_app_keys)
    repos = get_repositories(session)
    rows = await repos.conversation.list_messages(
        conversation_id, offset=offset, limit=min(limit, 200)
    )
    return [_to_msg_out(row) for row in rows]


async def _send_workflow_message(
    body: SendMessageBody,
    current: CurrentUser,
    session: AsyncSession,
    runtime: WorkflowRuntimeService,
    create_app_key: str,
) -> SendMessageOut:
    repos = get_repositories(session)
    if body.conversation_id is None:
        title = body.content[:64]
        conv = Conversation(
            user_id=current.id,
            title=title,
            app_key=create_app_key,
            flow_id=body.flow_id,
            status="active",
            metadata_=body.metadata or {},
        )
        await repos.conversation.conversation.add(conv)
    else:
        conv = await _owned_conversation(
            session, current, body.conversation_id, WORKFLOW_APP_KEYS
        )
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
    await session.commit()

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
    return SendMessageOut(
        conversation_id=conv.id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
        run_id=run_id,
    )


# --- planner（静态前缀须在 /{id} 之前） ---


@router.get("/planner", response_model=list[ConversationOut])
async def list_planner_conversations(
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ConversationOut]:
    return await _list_conversations(session, current, PLANNER_APP_KEYS, offset, limit)


@router.post("/planner", response_model=ConversationDetailOut)
async def create_planner_conversation(
    body: PlannerConversationCreateBody,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
) -> ConversationDetailOut:
    await _ensure_profile_usable(session, current, body.profile_id)
    extra = dict(body.metadata or {})
    extra["profile_id"] = str(body.profile_id)
    repos = get_repositories(session)
    conv = Conversation(
        user_id=current.id,
        title=body.title,
        app_key=APP_KEY_PLANNER,
        flow_id=None,
        status="active",
        metadata_=extra,
    )
    await repos.conversation.conversation.add(conv)
    return _to_conv_detail(conv)


@router.post("/planner/messages", response_model=SendMessageOut)
async def send_planner_message(
    body: PlannerSendMessageBody,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
    runtime: WorkflowRuntimeService = Depends(get_workflow_runtime),
) -> SendMessageOut:
    repos = get_repositories(session)
    profile_id = body.profile_id
    extra_meta = dict(body.metadata or {})
    if body.conversation_id is None:
        if profile_id is None:
            raise http_error(400, "profile_id_required", "发消息需要 profile_id")
        await _ensure_profile_usable(session, current, profile_id)
        extra_meta["profile_id"] = str(profile_id)
        conv = Conversation(
            user_id=current.id,
            title=body.content[:64],
            app_key=APP_KEY_PLANNER,
            flow_id=None,
            status="active",
            metadata_=extra_meta,
        )
        await repos.conversation.conversation.add(conv)
    else:
        conv = await _owned_conversation(
            session, current, body.conversation_id, PLANNER_APP_KEYS
        )
        if profile_id is None:
            profile_id = _metadata_profile_id(dict(conv.metadata_))
        if extra_meta:
            conv.metadata_ = {**dict(conv.metadata_), **extra_meta}
        if profile_id is not None:
            conv.metadata_ = {**dict(conv.metadata_), "profile_id": str(profile_id)}
    if profile_id is None:
        raise http_error(400, "profile_id_required", "发消息需要 profile_id")
    await _ensure_profile_usable(session, current, profile_id)

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
    await session.commit()

    run_id = await runtime.start(
        StartRunRequest(
            user_id=current.id,
            flow_id=profile_id,
            conversation_id=conv.id,
            kind="planner",
            profile_id=profile_id,
            input_payload=RunStatePayload(
                messages=[{"role": "user", "content": body.content}],
                variables={"input": body.content},
                metadata={
                    "app_key": conv.app_key,
                    "assistant_message_id": str(assistant_msg.id),
                    "profile_id": str(profile_id),
                },
            ),
        )
    )
    return SendMessageOut(
        conversation_id=conv.id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
        run_id=run_id,
    )


@router.get("/planner/{conversation_id}", response_model=ConversationDetailOut)
async def get_planner_conversation(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
) -> ConversationDetailOut:
    conv = await _owned_conversation(session, current, conversation_id, PLANNER_APP_KEYS)
    return _to_conv_detail(conv)


@router.get("/planner/{conversation_id}/messages", response_model=list[MessageOut])
async def list_planner_messages(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 100,
) -> list[MessageOut]:
    return await _list_messages(
        session, current, conversation_id, PLANNER_APP_KEYS, offset, limit
    )


@router.get("/planner/{conversation_id}/events")
async def subscribe_planner_events(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation_sse),
) -> StreamingResponse:
    async with session_scope() as session:
        await _owned_conversation(session, current, conversation_id, PLANNER_APP_KEYS)
    return _sse_response(conversation_id)


@router.delete("/planner/{conversation_id}")
async def delete_planner_conversation(
    conversation_id: UUID,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await _soft_delete_owned(session, current, conversation_id, PLANNER_APP_KEYS)
    return {"status": "deleted"}


@router.get("/workflow", response_model=list[ConversationOut])
async def list_workflow_conversations(
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ConversationOut]:
    return await _list_conversations(session, current, WORKFLOW_APP_KEYS, offset, limit)


@router.post("/workflow", response_model=ConversationOut)
async def create_workflow_conversation(
    body: ConversationCreateBody,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
) -> ConversationOut:
    repos = get_repositories(session)
    conv = Conversation(
        user_id=current.id,
        title=body.title,
        app_key=APP_KEY_WORKFLOW,
        flow_id=body.flow_id,
        status="active",
        metadata_=body.metadata or {},
    )
    await repos.conversation.conversation.add(conv)
    return _to_conv_out(conv)


@router.post("/workflow/messages", response_model=SendMessageOut)
async def send_workflow_message(
    body: SendMessageBody,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
    runtime: WorkflowRuntimeService = Depends(get_workflow_runtime),
) -> SendMessageOut:
    return await _send_workflow_message(
        body, current, session, runtime, APP_KEY_WORKFLOW
    )


@router.get("/workflow/hitl-pendings", response_model=list[HitlPendingOut])
async def list_workflow_hitl_pendings(
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    run_id: UUID | None = None,
) -> list[HitlPendingOut]:
    repos = get_repositories(session)
    owner_id = None if await _current_is_superuser(session, current) else current.id
    rows = await repos.workflow.list_pending_hitl(user_id=owner_id, run_id=run_id)
    result: list[HitlPendingOut] = []
    for pending in rows:
        run = await repos.workflow.run.get(pending.run_id)
        if run is None:
            continue
        result.append(_to_hitl_out(pending, run))
    return result


@router.get("/workflow/hitl-pendings/{hitl_id}", response_model=HitlPendingOut)
async def get_workflow_hitl_pending(
    hitl_id: UUID,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
) -> HitlPendingOut:
    pending, run = await _hitl_visible(session, current, hitl_id)
    return _to_hitl_out(pending, run)


@router.post("/workflow/hitl-pendings/{hitl_id}/resume", response_model=HitlResumeOut)
async def resume_workflow_hitl(
    hitl_id: UUID,
    body: HitlResumeBody,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    runtime: WorkflowRuntimeService = Depends(get_workflow_runtime),
) -> HitlResumeOut:
    pending, _run = await _hitl_visible(session, current, hitl_id)
    if pending.status != HITL_PENDING:
        raise http_error(400, "hitl_not_resumable", "待办不可恢复")
    output = await runtime.resume(
        HitlResumeInput(hitl_id=pending.id, decision=body.decision, user_input=body.user_input)
    )
    return HitlResumeOut(run_id=output.run_id, resumed=output.resumed)


@router.get("/workflow/{conversation_id}", response_model=ConversationDetailOut)
async def get_workflow_conversation(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
) -> ConversationDetailOut:
    conv = await _owned_conversation(session, current, conversation_id, WORKFLOW_APP_KEYS)
    return _to_conv_detail(conv)


@router.get("/workflow/{conversation_id}/messages", response_model=list[MessageOut])
async def list_workflow_messages(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 100,
) -> list[MessageOut]:
    return await _list_messages(
        session, current, conversation_id, WORKFLOW_APP_KEYS, offset, limit
    )


@router.get("/workflow/{conversation_id}/events")
async def subscribe_workflow_events(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation_sse),
) -> StreamingResponse:
    async with session_scope() as session:
        await _owned_conversation(session, current, conversation_id, WORKFLOW_APP_KEYS)
    return _sse_response(conversation_id)


@router.delete("/workflow/{conversation_id}")
async def delete_workflow_conversation(
    conversation_id: UUID,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await _soft_delete_owned(session, current, conversation_id, WORKFLOW_APP_KEYS)
    return {"status": "deleted"}


# --- 兼容别名：与 /workflow* 相同 ---


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[ConversationOut]:
    return await _list_conversations(session, current, WORKFLOW_APP_KEYS, offset, limit)


@router.post("", response_model=ConversationOut)
async def create_conversation(
    body: ConversationCreateBody,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
) -> ConversationOut:
    repos = get_repositories(session)
    conv = Conversation(
        user_id=current.id,
        title=body.title,
        app_key=APP_KEY_CONVERSATION_LEGACY,
        flow_id=body.flow_id,
        status="active",
        metadata_=body.metadata or {},
    )
    await repos.conversation.conversation.add(conv)
    return _to_conv_out(conv)


@router.post("/messages", response_model=SendMessageOut)
async def send_message(
    body: SendMessageBody,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
    runtime: WorkflowRuntimeService = Depends(get_workflow_runtime),
) -> SendMessageOut:
    create_key = (
        body.app_key
        if body.app_key in WORKFLOW_APP_KEYS
        else APP_KEY_CONVERSATION_LEGACY
    )
    return await _send_workflow_message(body, current, session, runtime, create_key)


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
) -> ConversationDetailOut:
    conv = await _owned_conversation(session, current, conversation_id, WORKFLOW_APP_KEYS)
    return _to_conv_detail(conv)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 100,
) -> list[MessageOut]:
    return await _list_messages(
        session, current, conversation_id, WORKFLOW_APP_KEYS, offset, limit
    )


@router.get("/{conversation_id}/events")
async def subscribe_events(
    conversation_id: UUID,
    current: CurrentUser = Depends(_use_conversation_sse),
) -> StreamingResponse:
    async with session_scope() as session:
        await _owned_conversation(session, current, conversation_id, WORKFLOW_APP_KEYS)
    return _sse_response(conversation_id)


@router.delete("/{conversation_id}")
async def delete_legacy_conversation(
    conversation_id: UUID,
    current: CurrentUser = Depends(_ctrl_conversation),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    await _soft_delete_owned(session, current, conversation_id, WORKFLOW_APP_KEYS)
    return {"status": "deleted"}
