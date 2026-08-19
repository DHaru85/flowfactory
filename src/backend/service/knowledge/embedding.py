"""OpenAI 兼容 Embedding 客户端。"""

from __future__ import annotations

import hashlib
from typing import Protocol

from loguru import logger
from openai import AsyncOpenAI

from settings.config import get_settings


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。"""


class OpenAICompatEmbeddingClient:
    """对接 vLLM OpenAI embeddings（如 bge-m3）。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        cfg = get_settings()
        self._model = model or cfg.embedding_model
        self._expected_dim = cfg.embedding_dim
        self._client = AsyncOpenAI(
            base_url=base_url or cfg.embedding_base_url,
            api_key=api_key if api_key is not None else cfg.embedding_api_key_or_empty_placeholder,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        logger.debug("调用 embedding model={} n={}", self._model, len(texts))
        response = await self._client.embeddings.create(model=self._model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        for vector in vectors:
            if len(vector) != self._expected_dim:
                raise ValueError(
                    f"embedding 维度 {len(vector)} 与配置 {self._expected_dim} 不一致"
                )
        return vectors


class FakeEmbeddingClient:
    """确定性伪向量，维度与配置一致。"""

    def __init__(self, dim: int | None = None) -> None:
        self._dim = dim if dim is not None else get_settings().embedding_dim
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [_hash_vector(text, self._dim) for text in texts]


def _hash_vector(text: str, dim: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    seed = digest
    while len(values) < dim:
        for byte in seed:
            values.append((byte / 127.5) - 1.0)
            if len(values) >= dim:
                break
        seed = hashlib.sha256(seed).digest()
    norm = sum(v * v for v in values) ** 0.5
    if norm == 0:
        return values
    return [v / norm for v in values]


_override: EmbeddingClient | None = None


def set_embedding_client_override(client: EmbeddingClient | None) -> None:
    global _override
    _override = client


def get_embedding_client() -> EmbeddingClient:
    if _override is not None:
        return _override
    return OpenAICompatEmbeddingClient()
