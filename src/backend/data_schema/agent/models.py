"""Agent 配置域 ORM 模型。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_schema.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentLlm(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_llm"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    profiles: Mapped[list["AgentProfile"]] = relationship(back_populates="default_llm")


class AgentMcpServer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_mcp_server"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tools: Mapped[list["AgentTool"]] = relationship(back_populates="mcp_server")


class AgentSkill(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_skill"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentTool(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_tool"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_: Mapped[dict[str, object]] = mapped_column("schema", JSONB, nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    mcp_server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_mcp_server.id"),
        nullable=True,
    )

    mcp_server: Mapped["AgentMcpServer | None"] = relationship(back_populates="tools")


class AgentProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_profile"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    default_llm_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_llm.id"),
        nullable=True,
    )
    skill_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    owner_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_organization.id"),
        nullable=True,
    )

    default_llm: Mapped["AgentLlm | None"] = relationship(back_populates="profiles")
    flows: Mapped[list["AgentFlow"]] = relationship(back_populates="profile")


class AgentFlow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_flow"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_agent_flow_code_version"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_profile.id"),
        nullable=False,
    )
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["AgentProfile"] = relationship(back_populates="flows")
    beat_tasks: Mapped[list["AgentBeatTask"]] = relationship(back_populates="flow")
    checkpoint_schemas: Mapped[list["AgentCheckpointSchema"]] = relationship(
        back_populates="flow"
    )


class AgentBeatTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_beat_task"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_flow.id"),
        nullable=False,
    )
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    flow: Mapped["AgentFlow"] = relationship(back_populates="beat_tasks")


class AgentCheckpointSchema(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "agent_checkpoint_schema"

    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_flow.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state_schema: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    flow: Mapped["AgentFlow"] = relationship(back_populates="checkpoint_schemas")
