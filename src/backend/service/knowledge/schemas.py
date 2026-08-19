"""知识检索序列化对象。"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

HitSource = Literal["vector", "fulltext"]


class ChunkerOptions(BaseModel):
    """切片策略与窗口，均可覆盖全局默认。"""

    strategy: str | None = None
    chunk_size: int | None = Field(default=None, ge=32)
    chunk_overlap: int | None = Field(default=None, ge=0)


class SectionDraft(BaseModel):
    heading: str | None = None
    char_start: int
    char_end: int
    ordinal: int = 0


class ChunkDraft(BaseModel):
    content: str
    ordinal: int
    token_count: int
    section_ordinal: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ChunkParseResult(BaseModel):
    sections: list[SectionDraft]
    chunks: list[ChunkDraft]


class EmbeddingInput(BaseModel):
    chunk_ids: list[uuid.UUID]
    texts: list[str]
    model: str


class EmbeddingOutput(BaseModel):
    vectors: list[list[float]]
    dimensions: int


class ChunkRef(BaseModel):
    chunk_id: uuid.UUID


class SearchQuery(BaseModel):
    collection_ids: list[uuid.UUID]
    query_text: str
    top_k: int = 20
    filters: dict[str, object] | None = None


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    doc_id: uuid.UUID
    score: float
    source: HitSource
    snippet: str
    content: str = ""


class SearchHitList(BaseModel):
    hits: list[SearchHit]


class RerankResult(BaseModel):
    hits: list[SearchHit]
    model: str


class IngestionJobStats(BaseModel):
    chunks: int = 0
    embedded: int = 0
    indexed: int = 0
    skipped: bool = False


class IngestDocumentRequest(BaseModel):
    job_id: uuid.UUID
    doc_id: uuid.UUID
    chunker: ChunkerOptions | None = None
