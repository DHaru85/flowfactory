"""PDF 按页抽取文本。"""

from __future__ import annotations

from io import BytesIO

from loguru import logger


def is_pdf_bytes(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def build_simple_pdf(text: str, *, extra_pages: list[str] | None = None) -> bytes:
    """构造可被 pypdf 解析的最小 PDF（Helvetica Type1，适合 ASCII 测试句）。"""
    pages = [text, *(extra_pages or [])]
    bodies: list[str] = []
    for page_text in pages:
        safe = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        bodies.append(f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET\n")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kid_refs = " ".join(f"{3 + index} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kid_refs}] /Count {len(pages)} >>".encode())
    content_ids = [3 + len(pages) + index for index in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    for content_id in content_ids:
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
            ).encode()
        )
    for body in bodies:
        payload = body.encode("latin-1")
        objects.append(f"<< /Length {len(payload)} >>\nstream\n".encode() + payload + b"endstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for pos in offsets[1:]:
        out.extend(f"{pos:010d} 00000 n \n".encode())
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    )
    out.extend(trailer.encode())
    return bytes(out)


def extract_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """返回 (页码从 1 起, 文本)。"""
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("PDF 第 {} 页抽取失败: {}", index + 1, exc)
            text = ""
        pages.append((index + 1, text.replace("\x00", "")))
    return pages
