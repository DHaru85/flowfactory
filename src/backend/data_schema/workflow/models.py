"""Workflow 域 ORM 模型。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from data_schema.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ThreadSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "wf_thread_snapshot"

    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    queue_name: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class RunSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "wf_run_snapshot"
    __table_args__ = (
        Index("idx_wf_run_user", "user_id", "created_at"),
        Index("idx_wf_run_conv", "conversation_id"),
    )

    flow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_user.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    langgraph_thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HitlPending(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "wf_hitl_pending"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    resume_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CeleryTaskRecord(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "wf_celery_task_record"

    celery_task_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
