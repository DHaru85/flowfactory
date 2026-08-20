"""新增 agent_resource_binding（配置资源与 RBAC 主体绑定）

Revision ID: e4a1b8c27d90
Revises: b7e2c91a4d03
Create Date: 2026-08-20 09:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4a1b8c27d90"
down_revision: Union[str, Sequence[str], None] = "b7e2c91a4d03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_resource_binding",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("resource_type", sa.String(length=16), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default="now()", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default="now()", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_type",
            "resource_id",
            "subject_type",
            "subject_id",
            name="uq_agent_resource_binding_subject",
        ),
    )
    op.create_index(
        "idx_agent_resource_binding_resource",
        "agent_resource_binding",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_resource_binding_resource", table_name="agent_resource_binding")
    op.drop_table("agent_resource_binding")
