"""新增 agent_resource_binding 主体查询索引。

Revision ID: b1d8f4a06c31
Revises: a9c3e1d04b72
Create Date: 2026-08-20 15:20:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b1d8f4a06c31"
down_revision: Union[str, Sequence[str], None] = "a9c3e1d04b72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_agent_resource_binding_subject",
        "agent_resource_binding",
        ["resource_type", "subject_type", "subject_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_resource_binding_subject", table_name="agent_resource_binding")
