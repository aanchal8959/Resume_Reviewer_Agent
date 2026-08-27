"""PDF/TXT text extraction with strict validation.

Primary engine is PyMuPDF (fitz) as specified; if its native wheel cannot be
loaded on the host (rare Windows runtime issue), extraction transparently falls
back to the pure-Python ``pypdf`` package so the app keeps working everywhere.
"""

from __future__ import annotations

import io

try:  # pragma: no cover - exercised implicitly on every platform
    import fitz  # PyMuPDF

    fitz.open  # force attribute access inside the guarded import
    _HAVE_PYMUPDF = True
except (ImportError, AttributeError, OSError):
    fitz = None  # type: ignore[assignment]
    _HAVE_PYMUPDF = False

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - depends on env
    PdfReader = None  # type: ignore[assignment]

PDF_MAGIC = b"%PDF"


class DocumentParseError(Exception):
    """Raised for invalid, empty or unreadable documents."""


def _require_engine() -> None:
    if not _HAVE_PYMUPDF and PdfReader is None:
        raise DocumentParseError(
            "No PDF engine available. Install 'PyMuPDF' (preferred) or 'pypdf'."
        )


def extract_pdf_text(content: bytes) -> str:
    """Extract text from all pages of a PDF."""
    _require_engine()
    if not content.startswith(PDF_MAGIC):
        raise DocumentParseError("File does not look like a valid PDF (missing %PDF header).")

    pages: list[str] | None = None
    if _HAVE_PYMUPDF:
        try:
            with fitz.open(stream=content, filetype="pdf") as doc:  # type: ignore[union-attr]
                if doc.page_count == 0:
                    raise DocumentParseError("PDF contains no pages.")
                pages = [page.get_text("text") for page in doc]
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:  # type: ignore[union-attr]
            last_error: Exception | None = exc
        except DocumentParseError:
            raise
        else:
            last_error = None
            text = "\n".join(pages).strip()
            if text:
                return text
    else:
        last_error = None

    return _extract_with_pypdf(content, previous_error=last_error)


def _extract_with_pypdf(content: bytes, previous_error: Exception | None) -> str:
    """Fallback extractor (also used when PyMuPDF yields no text)."""
    if PdfReader is None:
        if previous_error is not None:
            raise DocumentParseError(f"Corrupt or unreadable PDF file: {previous_error}")
        raise DocumentParseError(
            "No extractable text found in the PDF. It may be a scanned image."
        )
    try:
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) == 0:
            raise DocumentParseError("PDF contains no pages.")
        pages = [(page.extract_text() or "") for page in reader.pages]
    except DocumentParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf raises many exception types
        raise DocumentParseError(f"Corrupt or invalid PDF file: {exc}") from exc

    text = "\n".join(pages).strip()
    if not text:
        raise DocumentParseError(
            "No extractable text found in the PDF. It may be a scanned image."
        )
    return text


def extract_txt_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")
    return text.strip()


def parse_document(filename: str, content_type: str, content: bytes) -> str:
    """Dispatch on file type; validates size/emptiness at this boundary."""
    del content_type
    if len(content) == 0:
        raise DocumentParseError("Uploaded file is empty.")
    lowered = filename.lower()
    if lowered.endswith(".pdf") or content[:5] == PDF_MAGIC:
        return extract_pdf_text(content)
    if lowered.endswith(".txt"):
        text = extract_txt_text(content)
        if not text:
            raise DocumentParseError("Uploaded TXT file contains no text.")
        return text
    raise DocumentParseError(
        f"Unsupported file type '{filename}'. Upload a PDF or TXT file."
    )


# ---------------------------------------------------------------------------
# Minimal PDF writer (no external dependencies) used by tests and sample data.
# ---------------------------------------------------------------------------


def _escape_pdf_string(line: str) -> str:
    return line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_fake_pdf(text_lines: list[str], max_lines_per_page: int = 48) -> bytes:
    """Create a small valid PDF containing the given text lines."""
    chunks = [
        text_lines[i : i + max_lines_per_page]
        for i in range(0, max(1, len(text_lines)), max_lines_per_page)
    ] or [[]]

    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    def esc(value: str) -> bytes:
        return _escape_pdf_string(value).encode("latin-1", errors="replace")

    catalog_id = add(b"placeholder")  # id 1
    pages_id = add(b"placeholder")  # id 2
    font_id = add(b"placeholder")  # id 3 (font shared by pages)
    page_ids = [
        add(b"placeholder") for _ in chunks
    ]
    content_ids = []
    for chunk in chunks:
        parts = [b"BT /F1 11 Tf 14 TL 72 720 Td"]
        for line in chunk:
            parts.append(b"(" + esc(line) + b") Tj T*")
        parts.append(b"ET")
        stream = b" ".join(parts)
        content_ids.append(add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)))

    objects[catalog_id - 1] = (
        b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
    )
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    objects[pages_id - 1] = (
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))
    )
    objects[font_id - 1] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )
    for pid in page_ids:
        index = page_ids.index(pid)
        objects[pid - 1] = (
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_id, font_id, content_ids[index])
        )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0] * len(objects)
    for obj_number, body in enumerate(objects, start=1):
        offsets[obj_number - 1] = out.tell()
        out.write(b"%d 0 obj\n%s\nendobj\n" % (obj_number, body))

    xref_offset = out.tell()
    out.write(b"xref\n0 %d\n" % (len(objects) + 1))
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog_id, xref_offset)
    )
    return out.getvalue()
