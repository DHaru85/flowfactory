"""向量 + 全文检索与 RRF 融合。"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from service.knowledge.embedding import EmbeddingClient, get_embedding_client
from service.knowledge.rerank import Reranker, apply_rerank, get_reranker
from service.knowledge.schemas import RerankResult, SearchHit, SearchHitList, SearchQuery
from service.persistence.factory import get_repositories
from settings.config import get_settings


def _snippet(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _split_filters(
    filters: dict[str, object] | None,
) -> tuple[uuid.UUID | None, dict[str, object] | None]:
    if not filters:
        return None, None
    doc_raw = filters.get("doc_id")
    doc_id: uuid.UUID | None = None
    if doc_raw is not None:
        doc_id = uuid.UUID(str(doc_raw))
    metadata = {key: value for key, value in filters.items() if key != "doc_id"}
    return doc_id, metadata or None


class RetrievalService:
    """双路召回、RRF、可选 ONNX 重排。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        embedder: EmbeddingClient | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._reranker = reranker

    async def search(self, query: SearchQuery) -> SearchHitList:
        cfg = get_settings()
        top_k = query.top_k or cfg.kb_retrieve_top_k
        doc_id, metadata = _split_filters(query.filters)
        repos = get_repositories(self._session)
        embedder = self._embedder or get_embedding_client()
        vectors = await embedder.embed([query.query_text])
        query_vec = vectors[0]

        vector_rows = await repos.knowledge.search_vector(
            query.collection_ids,
            query_vec,
            top_k=top_k,
            doc_id=doc_id,
            metadata_contains=metadata,
        )
        fulltext_rows = await repos.knowledge.search_fulltext(
            query.collection_ids,
            query.query_text,
            top_k=top_k,
            fts_config=cfg.kb_fts_config,
            doc_id=doc_id,
            metadata_contains=metadata,
        )
        hits: list[SearchHit] = []
        for chunk, score in vector_rows:
            hits.append(
                SearchHit(
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    score=score,
                    source="vector",
                    snippet=_snippet(chunk.content),
                    content=chunk.content,
                )
            )
        for chunk, score in fulltext_rows:
            hits.append(
                SearchHit(
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    score=score,
                    source="fulltext",
                    snippet=_snippet(chunk.content),
                    content=chunk.content,
                )
            )
        return SearchHitList(hits=hits)

    def fuse(self, hit_list: SearchHitList, *, rrf_k: int | None = None) -> SearchHitList:
        k = rrf_k if rrf_k is not None else get_settings().kb_rrf_k
        scores: dict[uuid.UUID, float] = defaultdict(float)
        chosen: dict[uuid.UUID, SearchHit] = {}
        for source in ("vector", "fulltext"):
            ranked = [hit for hit in hit_list.hits if hit.source == source]
            for rank, hit in enumerate(ranked, start=1):
                scores[hit.chunk_id] += 1.0 / (k + rank)
                previous = chosen.get(hit.chunk_id)
                if previous is None or hit.source == "vector":
                    chosen[hit.chunk_id] = hit
        fused = [
            chosen[chunk_id].model_copy(update={"score": score, "source": chosen[chunk_id].source})
            for chunk_id, score in scores.items()
        ]
        fused.sort(key=lambda item: item.score, reverse=True)
        return SearchHitList(hits=fused)

    def rerank(self, hit_list: SearchHitList, query: str) -> RerankResult:
        cfg = get_settings()
        reranker = self._reranker or get_reranker()
        trimmed = SearchHitList(hits=hit_list.hits[: cfg.kb_rerank_top_n])
        return apply_rerank(reranker, query, trimmed.hits)
