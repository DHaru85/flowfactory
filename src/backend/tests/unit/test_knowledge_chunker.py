"""切片策略与 PDF 解析单元测试。"""

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.knowledge.chunker import (  # noqa: E402
    UnknownChunkStrategyError,
    parse_text,
    resolve_chunker_options,
)
from service.knowledge.parser import parse_bytes  # noqa: E402
from service.knowledge.pdf import build_simple_pdf, is_pdf_bytes  # noqa: E402
from service.knowledge.schemas import ChunkerOptions  # noqa: E402

HELLO_PDF = build_simple_pdf("HelloPDFChunk")


def test_recursive_splits_headings() -> None:
    text = "# 标题甲\n" + ("段落内容。" * 40) + "\n# 标题乙\n短文"
    result = parse_text(text, ChunkerOptions(strategy="recursive", chunk_size=80, chunk_overlap=10))
    headings = {section.heading for section in result.sections}
    assert "标题甲" in headings
    assert "标题乙" in headings
    assert len(result.chunks) >= 2
    assert all(chunk.token_count >= 1 for chunk in result.chunks)


def test_markdown_keeps_short_section_as_one_chunk() -> None:
    text = "# A\nshort\n# B\nalso short"
    result = parse_text(text, ChunkerOptions(strategy="markdown", chunk_size=800, chunk_overlap=0))
    assert len(result.sections) == 2
    assert len(result.chunks) == 2


def test_fixed_ignores_headings_as_section_breaks() -> None:
    text = "# A\n" + ("x" * 50) + "\n# B\n" + ("y" * 50)
    result = parse_text(text, ChunkerOptions(strategy="fixed", chunk_size=40, chunk_overlap=0))
    assert len(result.sections) == 1
    assert len(result.chunks) >= 2


def test_page_strategy_uses_form_feed() -> None:
    text = "第一页内容\f第二页内容"
    result = parse_text(text, ChunkerOptions(strategy="page", chunk_size=800, chunk_overlap=0))
    assert len(result.sections) == 2
    assert result.sections[0].heading == "第1页"
    assert len(result.chunks) == 2


def test_unknown_strategy_raises() -> None:
    with pytest.raises(UnknownChunkStrategyError):
        resolve_chunker_options(ChunkerOptions(strategy="no-such"))


def test_empty_text() -> None:
    result = parse_text("", ChunkerOptions(strategy="recursive"))
    assert result.chunks == []


def test_pdf_bytes_detected_and_parsed() -> None:
    assert is_pdf_bytes(HELLO_PDF)
    result = parse_bytes(
        HELLO_PDF,
        mime_type="application/pdf",
        options=ChunkerOptions(strategy="page", chunk_size=800, chunk_overlap=0),
    )
    joined = " ".join(chunk.content for chunk in result.chunks)
    assert "HelloPDFChunk" in joined or "第1页" in joined
