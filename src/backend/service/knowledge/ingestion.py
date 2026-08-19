"""入库流水线。"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDoc,
    KnowledgeIngestionJob,
    KnowledgeSection,
)
from service.cache.client import get_redis_client
from service.cache.stores import KnowledgeCacheStore
from service.knowledge.embedding import EmbeddingClient, get_embedding_client
from service.knowledge.fulltext import index_chunk_fulltext
from service.knowledge.parser import parse_bytes
from service.knowledge.schemas import (
    ChunkParseResult,
    EmbeddingInput,
    EmbeddingOutput,
    IngestDocumentRequest,
    IngestionJobStats,
)
from service.persistence.factory import get_repositories
from service.storage.factory import get_object_store
from service.storage.protocol import ObjectStore
from settings.config import get_settings


class IngestionPipeline:
    """对应 kb_ingestion_job 的 Celery 侧执行器。"""

    def __init__(
        self,
        session: AsyncSession,
        request: IngestDocumentRequest,
        *,
        raw_bytes: bytes | None = None,
        store: ObjectStore | None = None,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._session = session
        self._request = request
        self._raw_bytes = raw_bytes
        self._store = store
        self._embedder = embedder
        self.job_id = request.job_id
        self.doc_id = request.doc_id

    async def fetch_raw(self) -> bytes:
        if self._raw_bytes is not None:
            return self._raw_bytes
        repos = get_repositories(self._session)
        doc = await repos.knowledge.doc.get(self.doc_id)
        if doc is None:
            raise ValueError(f"文档不存在: {self.doc_id}")
        if doc.storage_object_id is None:
            raise ValueError(f"文档缺少 storage_object_id: {self.doc_id}")
        storage = await repos.knowledge.storage_object.get(doc.storage_object_id)
        if storage is None:
            raise ValueError(f"存储对象不存在: {doc.storage_object_id}")
        store = self._store or get_object_store()
        return store.get(storage.bucket, storage.object_key)

    def parse(self, data: bytes, mime_type: str | None = None) -> ChunkParseResult:
        return parse_bytes(data, mime_type=mime_type, options=self._request.chunker)

    async def embed(self, payload: EmbeddingInput) -> EmbeddingOutput:
        client = self._embedder or get_embedding_client()
        vectors = await client.embed(payload.texts)
        dim = get_settings().embedding_dim
        if vectors and len(vectors[0]) != dim:
            raise ValueError(f"embedding 维度 {len(vectors[0])} 与配置 {dim} 不一致")
        return EmbeddingOutput(vectors=vectors, dimensions=dim)

    async def index_fulltext(self, chunk_ids: list) -> int:
        return await index_chunk_fulltext(self._session, chunk_ids)

    async def run(self) -> IngestionJobStats:
        repos = get_repositories(self._session)
        cache = KnowledgeCacheStore(get_redis_client())
        job = await repos.knowledge.ingestion_job.get(self.job_id)
        doc = await repos.knowledge.doc.get(self.doc_id)
        if job is None or doc is None:
            raise ValueError("入库任务或文档不存在")

        locked = cache.acquire_ingest_lock(self.doc_id)
        if not locked:
            logger.warning("文档 {} 入库锁未获得，跳过 job={}", self.doc_id, self.job_id)
            return IngestionJobStats(skipped=True)

        try:
            return await self._run_locked(repos, cache, job, doc)
        finally:
            cache.release_ingest_lock(self.doc_id)

    async def _run_locked(
        self,
        repos: object,
        cache: KnowledgeCacheStore,
        job: KnowledgeIngestionJob,
        doc: KnowledgeDoc,
    ) -> IngestionJobStats:
        knowledge = repos.knowledge  # type: ignore[attr-defined]
        now = datetime.now(UTC)
        job.status = "running"
        job.started_at = now
        job.error_message = None
        cache.set_ingest_progress(self.job_id, "stage", "running")
        await self._session.flush()

        try:
            raw = await self.fetch_raw()
            cache.set_ingest_progress(self.job_id, "stage", "parse")
            parsed = self.parse(raw, mime_type=_guess_mime(doc, raw))
            await knowledge.delete_doc_index(self.doc_id)

            section_ids: list = []
            for draft in parsed.sections:
                section = KnowledgeSection(
                    doc_id=self.doc_id,
                    ordinal=draft.ordinal,
                    heading=draft.heading,
                    char_start=draft.char_start,
                    char_end=draft.char_end,
                )
                await knowledge.section.add(section)
                section_ids.append(section)

            chunk_rows: list[KnowledgeChunk] = []
            section_by_ordinal = {item.ordinal: item for item in section_ids}
            for draft in parsed.chunks:
                section = None
                if draft.section_ordinal is not None:
                    section = section_by_ordinal.get(draft.section_ordinal)
                row = KnowledgeChunk(
                    collection_id=doc.collection_id,
                    doc_id=self.doc_id,
                    section_id=section.id if section is not None else None,
                    ordinal=draft.ordinal,
                    content=draft.content,
                    token_count=draft.token_count,
                    metadata_=draft.metadata,
                )
                await knowledge.chunk.add(row)
                chunk_rows.append(row)

            cache.set_ingest_progress(self.job_id, "chunks", str(len(chunk_rows)))
            cfg = get_settings()
            embedded = 0
            batch = max(1, cfg.embedding_batch_size)
            for start in range(0, len(chunk_rows), batch):
                group = chunk_rows[start : start + batch]
                payload = EmbeddingInput(
                    chunk_ids=[item.id for item in group],
                    texts=[item.content for item in group],
                    model=cfg.embedding_model,
                )
                output = await self.embed(payload)
                for row, vector in zip(group, output.vectors, strict=True):
                    row.embedding = vector
                    embedded += 1
                cache.set_ingest_progress(self.job_id, "embedded", str(embedded))
            await self._session.flush()

            indexed = await self.index_fulltext([item.id for item in chunk_rows])
            doc.status = "indexed"
            job.status = "success"
            job.stats = {
                "chunks": len(chunk_rows),
                "embedded": embedded,
                "indexed": indexed,
            }
            job.finished_at = datetime.now(UTC)
            cache.set_ingest_progress(self.job_id, "stage", "success")
            await self._session.flush()
            return IngestionJobStats(
                chunks=len(chunk_rows),
                embedded=embedded,
                indexed=indexed,
            )
        except Exception as exc:
            await self._fail(job, doc, cache, str(exc))
            return IngestionJobStats()

    async def _fail(
        self,
        job: KnowledgeIngestionJob,
        doc: KnowledgeDoc,
        cache: KnowledgeCacheStore,
        message: str,
    ) -> None:
        logger.exception("入库失败 job={} doc={} err={}", self.job_id, self.doc_id, message)
        job.status = "failed"
        job.error_message = message[:4000]
        job.finished_at = datetime.now(UTC)
        doc.status = "failed"
        cache.set_ingest_progress(self.job_id, "stage", "failed")
        await self._session.flush()


def _guess_mime(doc: KnowledgeDoc, raw: bytes) -> str | None:
    from service.knowledge.pdf import is_pdf_bytes

    if is_pdf_bytes(raw):
        return "application/pdf"
    meta = doc.metadata_ if isinstance(doc.metadata_, dict) else {}
    mime = meta.get("mime_type")
    return str(mime) if mime else None
