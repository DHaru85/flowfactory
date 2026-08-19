"""新增 wf_child_run_pending（子图独立 Run 等待）

Revision ID: b7e2c91a4d03
Revises: c4a91f2e7b10
Create Date: 2026-08-19 18:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e2c91a4d03"
down_revision: Union[str, Sequence[str], None] = "c4a91f2e7b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wf_child_run_pending",
        sa.Column("parent_run_id", sa.UUID(), nullable=False),
        sa.Column("child_run_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default="now()", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_wf_child_parent", "wf_child_run_pending", ["parent_run_id"])
    op.create_index("idx_wf_child_child", "wf_child_run_pending", ["child_run_id"], unique=True)
    op.create_index(
        "idx_wf_child_timeout",
        "wf_child_run_pending",
        ["timeout_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("idx_wf_child_timeout", table_name="wf_child_run_pending")
    op.drop_index("idx_wf_child_child", table_name="wf_child_run_pending")
    op.drop_index("idx_wf_child_parent", table_name="wf_child_run_pending")
    op.drop_table("wf_child_run_pending")
