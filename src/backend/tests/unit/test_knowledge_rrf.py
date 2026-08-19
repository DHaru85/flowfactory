"""RRF 与重排单元测试。"""

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.knowledge.rerank import (  # noqa: E402
    FakeReranker,
    IdentityReranker,
    apply_rerank,
    get_reranker,
    set_reranker_override,
)
from service.knowledge.retrieval import RetrievalService  # noqa: E402
from service.knowledge.schemas import SearchHit, SearchHitList  # noqa: E402
from settings.config import get_settings, reset_settings  # noqa: E402


def _hit(source: str, snippet: str, score: float) -> SearchHit:
    chunk_id = uuid4()
    return SearchHit(
        chunk_id=chunk_id,
        doc_id=uuid4(),
        score=score,
        source=source,  # type: ignore[arg-type]
        snippet=snippet,
        content=snippet,
    )


def test_rrf_prefers_overlap() -> None:
    shared = uuid4()
    doc = uuid4()
    vector_only = SearchHit(
        chunk_id=uuid4(),
        doc_id=doc,
        score=0.9,
        source="vector",
        snippet="v",
        content="v",
    )
    both_v = SearchHit(
        chunk_id=shared,
        doc_id=doc,
        score=0.8,
        source="vector",
        snippet="both",
        content="both",
    )
    both_f = SearchHit(
        chunk_id=shared,
        doc_id=doc,
        score=0.1,
        source="fulltext",
        snippet="both",
        content="both",
    )
    service = RetrievalService(session=None)  # type: ignore[arg-type]
    fused = service.fuse(SearchHitList(hits=[both_v, vector_only, both_f]), rrf_k=60)
    assert fused.hits[0].chunk_id == shared


def test_identity_rerank_keeps_order() -> None:
    hits = [_hit("vector", "a", 1.0), _hit("vector", "b", 0.5)]
    result = apply_rerank(IdentityReranker(), "q", hits)
    assert [item.snippet for item in result.hits] == ["a", "b"]
    assert result.model == "identity"


def test_fake_reranker_promotes_keyword() -> None:
    hits = [_hit("vector", "foo", 1.0), _hit("vector", "bar bar", 0.9)]
    result = apply_rerank(FakeReranker("bar"), "q", hits)
    assert result.hits[0].snippet == "bar bar"


def test_default_reranker_is_identity_without_onnx() -> None:
    reset_settings()
    set_reranker_override(None)
    assert get_settings().kb_rerank_onnx_path == ""
    assert get_reranker().model_name == "identity"
