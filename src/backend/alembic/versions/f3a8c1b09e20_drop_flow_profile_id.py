"""agent_flow 去掉整图 profile_id。

Revision ID: f3a8c1b09e20
Revises: b1d8f4a06c31
Create Date: 2026-09-10 11:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a8c1b09e20"
down_revision: Union[str, Sequence[str], None] = "b1d8f4a06c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("agent_flow"):
        if fk.get("constrained_columns") == ["profile_id"] and fk.get("name"):
            op.drop_constraint(fk["name"], "agent_flow", type_="foreignkey")
            break
    op.drop_column("agent_flow", "profile_id")


def downgrade() -> None:
    op.add_column("agent_flow", sa.Column("profile_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "agent_flow_profile_id_fkey",
        "agent_flow",
        "agent_profile",
        ["profile_id"],
        ["id"],
    )
