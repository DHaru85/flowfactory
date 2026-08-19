"""全文 tsvector 写入。"""

from __future__ import annotations

import uuid

from sqlalchemy import cast, func, update
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.knowledge.models import KnowledgeChunk
from settings.config import get_settings


def tsvector_expr(config_name: str, content_column: object) -> object:
    return func.to_tsvector(cast(config_name, REGCONFIG), content_column)


def tsquery_expr(config_name: str, query_text: str) -> object:
    return func.plainto_tsquery(cast(config_name, REGCONFIG), query_text)


async def index_chunk_fulltext(
    session: AsyncSession,
    chunk_ids: list[uuid.UUID],
    *,
    fts_config: str | None = None,
) -> int:
    if not chunk_ids:
        return 0
    config_name = fts_config or get_settings().kb_fts_config
    stmt = (
        update(KnowledgeChunk)
        .where(KnowledgeChunk.id.in_(chunk_ids))
        .values(content_tsv=tsvector_expr(config_name, KnowledgeChunk.content))
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)
