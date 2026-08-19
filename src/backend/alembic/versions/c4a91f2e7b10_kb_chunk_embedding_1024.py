"""kb_chunk embedding 维度改为 1024（bge-m3）

Revision ID: c4a91f2e7b10
Revises: 00fe9d0489d1
Create Date: 2026-08-19 09:50:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c4a91f2e7b10"
down_revision: Union[str, Sequence[str], None] = "00fe9d0489d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE kb_chunk DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE kb_chunk ADD COLUMN embedding vector(1024)")


def downgrade() -> None:
    op.execute("ALTER TABLE kb_chunk DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE kb_chunk ADD COLUMN embedding vector(1536)")
