"""Knowledge 与文件域仓储。"""

import uuid
from collections.abc import Sequence
from typing import TypeVar

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.knowledge.models import (
    FileStorageObject,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDoc,
    KnowledgeIngestionJob,
    KnowledgeSection,
)
from service.persistence.base import Repository

T = TypeVar("T")


class KnowledgeRepository:
    """知识库与文件聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.collection = Repository(session, KnowledgeCollection)
        self.doc = Repository(session, KnowledgeDoc)
        self.section = Repository(session, KnowledgeSection)
        self.chunk = Repository(session, KnowledgeChunk)
        self.storage_object = Repository(session, FileStorageObject)
        self.ingestion_job = Repository(session, KnowledgeIngestionJob)

    async def get_collection_by_code(self, code: str) -> KnowledgeCollection | None:
        stmt = select(KnowledgeCollection).where(KnowledgeCollection.code == code)
        return await self._session.scalar(stmt)

    async def list_docs_by_collection(self, collection_id: uuid.UUID) -> list[KnowledgeDoc]:
        stmt = select(KnowledgeDoc).where(KnowledgeDoc.collection_id == collection_id)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_chunks_by_doc(self, doc_id: uuid.UUID) -> list[KnowledgeChunk]:
        stmt = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.doc_id == doc_id)
            .order_by(KnowledgeChunk.ordinal)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_sections_by_doc(self, doc_id: uuid.UUID) -> list[KnowledgeSection]:
        stmt = (
            select(KnowledgeSection)
            .where(KnowledgeSection.doc_id == doc_id)
            .order_by(KnowledgeSection.ordinal)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_storage_object(self, bucket: str, object_key: str) -> FileStorageObject | None:
        stmt = select(FileStorageObject).where(
            FileStorageObject.bucket == bucket,
            FileStorageObject.object_key == object_key,
        )
        return await self._session.scalar(stmt)

    async def list_pending_ingestion_jobs(self) -> list[KnowledgeIngestionJob]:
        stmt = select(KnowledgeIngestionJob).where(
            KnowledgeIngestionJob.status.in_(("pending", "running"))
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def delete_doc_index(self, doc_id: uuid.UUID) -> None:
        """删除文档已有 section/chunk，供重新入库。"""
        await self._session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
        await self._session.execute(
            delete(KnowledgeSection).where(KnowledgeSection.doc_id == doc_id)
        )
        await self._session.flush()

    async def update_chunk_embedding(
        self,
        chunk_id: uuid.UUID,
        embedding: list[float],
        content_tsv: object | None = None,
    ) -> KnowledgeChunk | None:
        chunk = await self._session.get(KnowledgeChunk, chunk_id)
        if chunk is None:
            return None
        chunk.embedding = embedding
        if content_tsv is not None:
            chunk.content_tsv = content_tsv
        await self._session.flush()
        return chunk

    def _filter_stmt(
        self,
        stmt: Select[T],
        *,
        collection_ids: Sequence[uuid.UUID],
        doc_id: uuid.UUID | None,
        metadata_contains: dict[str, object] | None,
    ) -> Select[T]:
        stmt = stmt.where(KnowledgeChunk.collection_id.in_(collection_ids))
        if doc_id is not None:
            stmt = stmt.where(KnowledgeChunk.doc_id == doc_id)
        if metadata_contains:
            stmt = stmt.join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            stmt = stmt.where(KnowledgeDoc.metadata_.op("@>")(metadata_contains))
        return stmt

    async def search_vector(
        self,
        collection_ids: Sequence[uuid.UUID],
        query_vector: list[float],
        *,
        top_k: int,
        doc_id: uuid.UUID | None = None,
        metadata_contains: dict[str, object] | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
        stmt = select(KnowledgeChunk, distance).where(KnowledgeChunk.embedding.is_not(None))
        stmt = self._filter_stmt(
            stmt,
            collection_ids=collection_ids,
            doc_id=doc_id,
            metadata_contains=metadata_contains,
        )
        stmt = stmt.order_by(distance).limit(top_k)
        result = await self._session.execute(stmt)
        rows: list[tuple[KnowledgeChunk, float]] = []
        for chunk, dist in result.all():
            score = 1.0 / (1.0 + float(dist))
            rows.append((chunk, score))
        return rows

    async def search_fulltext(
        self,
        collection_ids: Sequence[uuid.UUID],
        query_text: str,
        *,
        top_k: int,
        fts_config: str,
        doc_id: uuid.UUID | None = None,
        metadata_contains: dict[str, object] | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        from service.knowledge.fulltext import tsquery_expr

        tsq = tsquery_expr(fts_config, query_text)
        rank = func.ts_rank_cd(KnowledgeChunk.content_tsv, tsq)
        stmt = (
            select(KnowledgeChunk, rank)
            .where(KnowledgeChunk.content_tsv.is_not(None))
            .where(KnowledgeChunk.content_tsv.op("@@")(tsq))
        )
        stmt = self._filter_stmt(
            stmt,
            collection_ids=collection_ids,
            doc_id=doc_id,
            metadata_contains=metadata_contains,
        )
        stmt = stmt.order_by(rank.desc()).limit(top_k)
        result = await self._session.execute(stmt)
        return [(chunk, float(score or 0.0)) for chunk, score in result.all()]
