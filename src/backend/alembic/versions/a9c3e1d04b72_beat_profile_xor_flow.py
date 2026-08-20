"""agent_beat_task：flow_id 可空，增加 profile_id，恰一非空。

Revision ID: a9c3e1d04b72
Revises: e4a1b8c27d90
Create Date: 2026-08-20 14:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9c3e1d04b72"
down_revision: Union[str, Sequence[str], None] = "e4a1b8c27d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "agent_beat_task",
        "flow_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.add_column("agent_beat_task", sa.Column("profile_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_agent_beat_task_profile_id",
        "agent_beat_task",
        "agent_profile",
        ["profile_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_agent_beat_task_flow_xor_profile",
        "agent_beat_task",
        "(flow_id IS NULL) <> (profile_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_beat_task_flow_xor_profile", "agent_beat_task", type_="check")
    op.drop_constraint("fk_agent_beat_task_profile_id", "agent_beat_task", type_="foreignkey")
    op.drop_column("agent_beat_task", "profile_id")
    op.alter_column(
        "agent_beat_task",
        "flow_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
