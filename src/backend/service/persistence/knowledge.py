"""Knowledge 与文件域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.knowledge.models import (
    FileStorageObject,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDoc,
    KnowledgeIngestionJob,
)
from service.persistence.base import Repository


class KnowledgeRepository:
    """知识库与文件聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.collection = Repository(session, KnowledgeCollection)
        self.doc = Repository(session, KnowledgeDoc)
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
