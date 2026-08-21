"""软删清理。"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data_schema.conversation.models import Conversation  # noqa: E402
from data_schema.permission.models import Organization, User  # noqa: E402
from service.auth.password import hash_password  # noqa: E402
from service.database.session import session_scope  # noqa: E402
from service.persistence.purge import purge_expired_soft_deleted  # noqa: E402


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_expired_deleted_conversation() -> None:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"pg-{suffix}", name="pg", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"pg-{suffix}",
            display_name="pg",
            organization_id=org.id,
            status="active",
            password_hash=hash_password("pw-ok"),
            is_superuser=False,
        )
        session.add(user)
        await session.flush()
        conv = Conversation(
            user_id=user.id,
            title="gone",
            app_key="planner",
            status="deleted",
        )
        session.add(conv)
        await session.flush()
        conv_id = conv.id
        old = datetime.now(UTC) - timedelta(days=30)
        await session.execute(
            update(Conversation).where(Conversation.id == conv_id).values(updated_at=old)
        )

    async with session_scope() as session:
        stats = await purge_expired_soft_deleted(session)
        assert stats["conversations"] >= 1
        leftover = await session.get(Conversation, conv_id)
        assert leftover is None
