"""交叉编码器重排：ONNX 路径可配置。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from loguru import logger

from service.knowledge.schemas import RerankResult, SearchHit
from settings.config import get_settings


class Reranker(Protocol):
    @property
    def model_name(self) -> str: ...

    def score(self, query: str, texts: list[str]) -> list[float]:
        """对 (query, text) 打分，越高越相关。"""


class IdentityReranker:
    """保持原序。"""

    model_name = "identity"

    def score(self, query: str, texts: list[str]) -> list[float]:
        del query
        n = len(texts)
        return [float(n - index) for index in range(n)]


class FakeReranker:
    """测试替身：按关键词命中加权。"""

    def __init__(self, keyword: str = "") -> None:
        self.keyword = keyword
        self.model_name = "fake"

    def score(self, query: str, texts: list[str]) -> list[float]:
        needle = self.keyword or query
        return [float(text.count(needle)) for text in texts]


class OnnxCrossEncoderReranker:
    """从可配置路径加载 ONNX 交叉编码器。"""

    def __init__(
        self,
        onnx_path: str,
        tokenizer_path: str,
        max_length: int,
    ) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.model_name = Path(onnx_path).name
        self._np = np
        self._max_length = max_length
        tok_file = Path(tokenizer_path)
        if tok_file.is_dir():
            tok_file = tok_file / "tokenizer.json"
        self._tokenizer = Tokenizer.from_file(str(tok_file))
        self._session = ort.InferenceSession(
            onnx_path,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = [item.name for item in self._session.get_inputs()]

    def score(self, query: str, texts: list[str]) -> list[float]:
        scores: list[float] = []
        for text in texts:
            encoding = self._tokenizer.encode(query, text)
            ids = encoding.ids[: self._max_length]
            mask = encoding.attention_mask[: self._max_length]
            pad = self._max_length - len(ids)
            if pad > 0:
                ids = ids + [0] * pad
                mask = mask + [0] * pad
            feeds: dict[str, object] = {}
            array_ids = self._np.asarray([ids], dtype=self._np.int64)
            array_mask = self._np.asarray([mask], dtype=self._np.int64)
            for name in self._input_names:
                lowered = name.lower()
                if "mask" in lowered:
                    feeds[name] = array_mask
                elif "type" in lowered or "token_type" in lowered:
                    feeds[name] = self._np.zeros_like(array_ids)
                else:
                    feeds[name] = array_ids
            outputs = self._session.run(None, feeds)
            scores.append(_scalar(outputs[0]))
        return scores


def _scalar(value: object) -> float:
    if hasattr(value, "reshape"):
        flat = value.reshape(-1)  # type: ignore[union-attr]
        return float(flat[0])
    if isinstance(value, (list, tuple)):
        return _scalar(value[0])
    return float(value)  # type: ignore[arg-type]


def apply_rerank(reranker: Reranker, query: str, hits: list[SearchHit]) -> RerankResult:
    if not hits:
        return RerankResult(hits=[], model=reranker.model_name)
    texts = [hit.content or hit.snippet for hit in hits]
    scores = reranker.score(query, texts)
    ranked = sorted(
        zip(hits, scores, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    out: list[SearchHit] = []
    for hit, score in ranked:
        out.append(hit.model_copy(update={"score": float(score)}))
    return RerankResult(hits=out, model=reranker.model_name)


_override: Reranker | None = None


def set_reranker_override(reranker: Reranker | None) -> None:
    global _override
    _override = reranker


def get_reranker() -> Reranker:
    if _override is not None:
        return _override
    cfg = get_settings()
    path = cfg.kb_rerank_onnx_path.strip()
    tok = cfg.kb_rerank_tokenizer_path.strip()
    if not path:
        return IdentityReranker()
    if not Path(path).is_file():
        logger.error("ONNX 重排模型不存在 path={}", path)
        return IdentityReranker()
    if not tok:
        logger.error("已配置 ONNX 但未配置 kb_rerank_tokenizer_path，回退 Identity")
        return IdentityReranker()
    try:
        return OnnxCrossEncoderReranker(path, tok, cfg.kb_rerank_max_length)
    except Exception as exc:
        logger.exception("加载 ONNX 重排模型失败: {}", exc)
        return IdentityReranker()
