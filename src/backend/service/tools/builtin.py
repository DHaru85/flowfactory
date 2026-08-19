"""内置工具：知识检索。"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from service.knowledge.retrieval import RetrievalService
from service.knowledge.schemas import SearchQuery


async def kb_retrieve(session: AsyncSession, arguments: dict[str, object]) -> object:
    raw_ids = arguments.get("collection_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("collection_ids 必须为非空列表")
    collection_ids = [uuid.UUID(str(item)) for item in raw_ids]
    top_k_raw = arguments.get("top_k")
    top_k = int(top_k_raw) if top_k_raw is not None else 20
    filters_raw = arguments.get("filters")
    filters = filters_raw if isinstance(filters_raw, dict) else None
    query = SearchQuery(
        collection_ids=collection_ids,
        query_text=str(arguments.get("query_text") or ""),
        top_k=top_k,
        filters=filters,
    )
    hits = await RetrievalService(session).search(query)
    return [
        {
            "chunk_id": str(hit.chunk_id),
            "doc_id": str(hit.doc_id),
            "score": hit.score,
            "snippet": hit.snippet,
            "source": hit.source,
        }
        for hit in hits.hits
    ]
