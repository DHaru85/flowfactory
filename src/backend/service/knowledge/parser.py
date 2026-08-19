"""原文解码：PDF 或 UTF-8 文本。"""

from __future__ import annotations

from service.knowledge.chunker import parse_text
from service.knowledge.pdf import extract_pdf_pages, is_pdf_bytes
from service.knowledge.schemas import ChunkerOptions, ChunkParseResult


def decode_source(data: bytes, *, mime_type: str | None = None) -> str:
    """将原文字节转为带可选分页符的文本。"""
    looks_pdf = is_pdf_bytes(data) or (mime_type or "").lower() in {
        "application/pdf",
        "application/x-pdf",
    }
    if looks_pdf:
        pages = extract_pdf_pages(data)
        parts: list[str] = []
        for page_no, page_text in pages:
            heading = f"## 第{page_no}页\n"
            parts.append(heading + page_text.strip())
        return "\f".join(parts)
    return data.decode("utf-8", errors="replace")


def parse_bytes(
    data: bytes,
    *,
    mime_type: str | None = None,
    options: ChunkerOptions | None = None,
) -> ChunkParseResult:
    text = decode_source(data, mime_type=mime_type)
    return parse_text(text, options)
