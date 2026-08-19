"""可配置文本切片策略。"""

from __future__ import annotations

import re
from collections.abc import Callable

from service.knowledge.schemas import ChunkDraft, ChunkerOptions, ChunkParseResult, SectionDraft
from settings.config import get_settings

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_SEPARATORS = ("\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", " ")
KNOWN_STRATEGIES = frozenset({"recursive", "markdown", "fixed", "page"})


class UnknownChunkStrategyError(ValueError):
    """未知切片策略名。"""


def estimate_tokens(text: str) -> int:
    cjk = 0
    other_chars: list[str] = []
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            cjk += 1
        else:
            other_chars.append(char)
    rest = "".join(other_chars)
    words = len(rest.split()) if rest.strip() else 0
    return max(1, cjk + words) if text.strip() else 0


def _clip_overlap(size: int, overlap: int) -> int:
    if overlap < 0:
        return 0
    if overlap >= size:
        return max(0, size // 4)
    return overlap


def split_with_overlap(text: str, size: int, overlap: int) -> list[tuple[int, int, str]]:
    """在 text 上切出 (start, end, content)，end 为开区间。"""
    if not text:
        return []
    overlap = _clip_overlap(size, overlap)
    pieces: list[tuple[int, int, str]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + size)
        if end < length:
            window = text[start:end]
            split_at = _last_separator(window)
            if split_at >= size // 4:
                end = start + split_at
        chunk = text[start:end].strip()
        if chunk:
            rel_start = text.find(chunk, start)
            if rel_start < 0:
                rel_start = start
            pieces.append((rel_start, rel_start + len(chunk), chunk))
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return pieces


def _last_separator(window: str) -> int:
    for sep in _SEPARATORS:
        idx = window.rfind(sep)
        if idx > 0:
            return idx + len(sep)
    return len(window)


def split_markdown_sections(text: str) -> list[SectionDraft]:
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [SectionDraft(heading=None, char_start=0, char_end=len(text), ordinal=0)]
    sections: list[SectionDraft] = []
    if matches[0].start() > 0:
        prefix = text[: matches[0].start()].strip()
        if prefix:
            sections.append(
                SectionDraft(heading=None, char_start=0, char_end=matches[0].start(), ordinal=0)
            )
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(
            SectionDraft(
                heading=match.group(2).strip(),
                char_start=start,
                char_end=end,
                ordinal=len(sections),
            )
        )
    return sections


def split_page_sections(text: str) -> list[SectionDraft]:
    parts = text.split("\f")
    sections: list[SectionDraft] = []
    cursor = 0
    for index, part in enumerate(parts):
        end = cursor + len(part)
        if index < len(parts) - 1:
            end += 1
        heading = f"第{index + 1}页"
        if part.strip() or index == 0:
            sections.append(
                SectionDraft(heading=heading, char_start=cursor, char_end=end, ordinal=index)
            )
        cursor = end
    if not sections:
        sections.append(SectionDraft(heading="第1页", char_start=0, char_end=len(text), ordinal=0))
    return sections


def _chunks_from_sections(
    text: str,
    sections: list[SectionDraft],
    size: int,
    overlap: int,
    *,
    one_chunk_if_short: bool,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    ordinal = 0
    for section in sections:
        body = text[section.char_start : section.char_end]
        if one_chunk_if_short and len(body.strip()) <= size:
            content = body.strip()
            if not content:
                continue
            drafts.append(
                _draft(content, ordinal, section, section.char_start)
            )
            ordinal += 1
            continue
        for start, end, content in split_with_overlap(body, size, overlap):
            abs_start = section.char_start + start
            drafts.append(_draft(content, ordinal, section, abs_start))
            ordinal += 1
    return drafts


def _draft(content: str, ordinal: int, section: SectionDraft, char_start: int) -> ChunkDraft:
    metadata: dict[str, object] = {
        "char_start": char_start,
        "char_end": char_start + len(content),
        "heading": section.heading,
    }
    return ChunkDraft(
        content=content,
        ordinal=ordinal,
        token_count=estimate_tokens(content),
        section_ordinal=section.ordinal,
        metadata=metadata,
    )


def _parse_recursive(text: str, size: int, overlap: int) -> ChunkParseResult:
    sections = split_markdown_sections(text)
    chunks = _chunks_from_sections(text, sections, size, overlap, one_chunk_if_short=False)
    return ChunkParseResult(sections=sections, chunks=chunks)


def _parse_markdown(text: str, size: int, overlap: int) -> ChunkParseResult:
    sections = split_markdown_sections(text)
    chunks = _chunks_from_sections(text, sections, size, overlap, one_chunk_if_short=True)
    return ChunkParseResult(sections=sections, chunks=chunks)


def _parse_fixed(text: str, size: int, overlap: int) -> ChunkParseResult:
    sections = [SectionDraft(heading=None, char_start=0, char_end=len(text), ordinal=0)]
    chunks = _chunks_from_sections(text, sections, size, overlap, one_chunk_if_short=False)
    return ChunkParseResult(sections=sections, chunks=chunks)


def _parse_page(text: str, size: int, overlap: int) -> ChunkParseResult:
    sections = split_page_sections(text)
    chunks = _chunks_from_sections(text, sections, size, overlap, one_chunk_if_short=True)
    return ChunkParseResult(sections=sections, chunks=chunks)


_PARSERS: dict[str, Callable[[str, int, int], ChunkParseResult]] = {
    "recursive": _parse_recursive,
    "markdown": _parse_markdown,
    "fixed": _parse_fixed,
    "page": _parse_page,
}


def resolve_chunker_options(options: ChunkerOptions | None = None) -> tuple[str, int, int]:
    cfg = get_settings()
    strategy = (options.strategy if options and options.strategy else cfg.kb_chunk_strategy).lower()
    size = options.chunk_size if options and options.chunk_size is not None else cfg.kb_chunk_size
    overlap = (
        options.chunk_overlap
        if options and options.chunk_overlap is not None
        else cfg.kb_chunk_overlap
    )
    if strategy not in KNOWN_STRATEGIES:
        raise UnknownChunkStrategyError(f"未知切片策略: {strategy}")
    return strategy, size, overlap


def parse_text(text: str, options: ChunkerOptions | None = None) -> ChunkParseResult:
    strategy, size, overlap = resolve_chunker_options(options)
    return _PARSERS[strategy](text, size, overlap)
