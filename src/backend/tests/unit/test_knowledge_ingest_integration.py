"""知识入库与检索集成测试（Postgres + Redis，Fake embedding）。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data_schema.knowledge.models import (  # noqa: E402
    KnowledgeCollection,
    KnowledgeDoc,
    KnowledgeIngestionJob,
)
from service.cache.client import get_redis_client  # noqa: E402
from service.cache.keys import CacheKeys  # noqa: E402
from service.database.session import session_scope  # noqa: E402
from service.knowledge.embedding import FakeEmbeddingClient  # noqa: E402
from service.knowledge.ingestion import IngestionPipeline  # noqa: E402
from service.knowledge.retrieval import RetrievalService  # noqa: E402
from service.knowledge.schemas import (  # noqa: E402
    ChunkerOptions,
    IngestDocumentRequest,
    SearchQuery,
)
from service.persistence.factory import get_repositories  # noqa: E402
from tests.unit.test_knowledge_chunker import HELLO_PDF  # noqa: E402

SEED = "可配置知识检索基础设施建设语句"


async def _seed_doc(
    raw_status: str = "pending",
) -> tuple[KnowledgeCollection, KnowledgeDoc, KnowledgeIngestionJob]:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        repos = get_repositories(session)
        collection = KnowledgeCollection(
            code=f"kb-{suffix}",
            name="test-kb",
            embedding_model="bge-m3",
            status="active",
        )
        await repos.knowledge.collection.add(collection)
        doc = KnowledgeDoc(
            collection_id=collection.id,
            title=f"doc-{suffix}",
            source_type="upload",
            status=raw_status,
            metadata_={"lang": "zh"},
        )
        await repos.knowledge.doc.add(doc)
        job = KnowledgeIngestionJob(
            collection_id=collection.id,
            doc_id=doc.id,
            trigger="manual",
            status="pending",
            stats={},
        )
        await repos.knowledge.ingestion_job.add(job)
        session.expunge_all()
        return collection, doc, job


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ingest_markdown_and_search() -> None:
    collection, doc, job = await _seed_doc()
    markdown = f"# 说明\n{SEED}\n\n后续段落用于切分。"
    request = IngestDocumentRequest(
        job_id=job.id,
        doc_id=doc.id,
        chunker=ChunkerOptions(strategy="recursive", chunk_size=80, chunk_overlap=10),
    )
    embedder = FakeEmbeddingClient()
    async with session_scope() as session:
        pipeline = IngestionPipeline(
            session,
            request,
            raw_bytes=markdown.encode("utf-8"),
            embedder=embedder,
        )
        stats = await pipeline.run()
    assert stats.skipped is False
    assert stats.chunks >= 1
    assert stats.embedded == stats.chunks

    async with session_scope() as session:
        repos = get_repositories(session)
        stored_job = await repos.knowledge.ingestion_job.get(job.id)
        stored_doc = await repos.knowledge.doc.get(doc.id)
        chunks = await repos.knowledge.list_chunks_by_doc(doc.id)
        assert stored_job is not None and stored_job.status == "success"
        assert stored_doc is not None and stored_doc.status == "indexed"
        assert chunks
        assert chunks[0].embedding is not None
        assert len(chunks[0].embedding) == 1024
        assert chunks[0].content_tsv is not None

        service = RetrievalService(session, embedder=embedder)
        raw_hits = await service.search(
            SearchQuery(collection_ids=[collection.id], query_text=SEED, top_k=10)
        )
        fused = service.fuse(raw_hits)
        assert fused.hits
        contents = " ".join(hit.content for hit in fused.hits)
        assert "知识检索" in contents or SEED[:6] in contents

        filtered = await service.search(
            SearchQuery(
                collection_ids=[collection.id],
                query_text=SEED,
                top_k=10,
                filters={"doc_id": str(doc.id)},
            )
        )
        assert all(hit.doc_id == doc.id for hit in filtered.hits)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ingest_pdf_page_strategy() -> None:
    _collection, doc, job = await _seed_doc()
    request = IngestDocumentRequest(
        job_id=job.id,
        doc_id=doc.id,
        chunker=ChunkerOptions(strategy="page"),
    )
    async with session_scope() as session:
        pipeline = IngestionPipeline(
            session,
            request,
            raw_bytes=HELLO_PDF,
            embedder=FakeEmbeddingClient(),
        )
        stats = await pipeline.run()
    assert stats.chunks >= 1
    async with session_scope() as session:
        repos = get_repositories(session)
        stored = await repos.knowledge.ingestion_job.get(job.id)
        assert stored is not None
        assert stored.status == "success"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ingest_lock_skips_second() -> None:
    _collection, doc, job = await _seed_doc()
    redis = get_redis_client()
    redis.set(CacheKeys.ingest_lock(doc.id), "1", ex=60)
    try:
        request = IngestDocumentRequest(job_id=job.id, doc_id=doc.id)
        async with session_scope() as session:
            pipeline = IngestionPipeline(
                session,
                request,
                raw_bytes=SEED.encode("utf-8"),
                embedder=FakeEmbeddingClient(),
            )
            stats = await pipeline.run()
        assert stats.skipped is True
        async with session_scope() as session:
            repos = get_repositories(session)
            stored = await repos.knowledge.ingestion_job.get(job.id)
            assert stored is not None
            assert stored.status == "pending"
    finally:
        redis.delete(CacheKeys.ingest_lock(doc.id))
