"""知识切片、向量化与检索。"""

from service.knowledge.chunker import (
    KNOWN_STRATEGIES,
    UnknownChunkStrategyError,
    parse_text,
    resolve_chunker_options,
)
from service.knowledge.embedding import (
    FakeEmbeddingClient,
    get_embedding_client,
    set_embedding_client_override,
)
from service.knowledge.ingestion import IngestionPipeline
from service.knowledge.parser import parse_bytes
from service.knowledge.rerank import (
    FakeReranker,
    IdentityReranker,
    get_reranker,
    set_reranker_override,
)
from service.knowledge.retrieval import RetrievalService
from service.knowledge.schemas import (
    ChunkerOptions,
    IngestDocumentRequest,
    SearchQuery,
)

__all__ = [
    "KNOWN_STRATEGIES",
    "UnknownChunkStrategyError",
    "ChunkerOptions",
    "IngestDocumentRequest",
    "SearchQuery",
    "parse_text",
    "parse_bytes",
    "resolve_chunker_options",
    "FakeEmbeddingClient",
    "get_embedding_client",
    "set_embedding_client_override",
    "IngestionPipeline",
    "RetrievalService",
    "IdentityReranker",
    "FakeReranker",
    "get_reranker",
    "set_reranker_override",
]
