"""Tests for PDF/TXT parsing and validation."""

import pytest

from app.services.pdf_parser import (
    DocumentParseError,
    build_fake_pdf,
    extract_pdf_text,
    parse_document,
)


def test_valid_pdf_extraction():
    pdf = build_fake_pdf(["Hello Resume", "Python FastAPI"])
    text = extract_pdf_text(pdf)
    assert "Hello Resume" in text
    assert "Python FastAPI" in text


def test_invalid_pdf_rejected():
    with pytest.raises(DocumentParseError):
        extract_pdf_text(b"this is not a pdf at all")


def test_empty_bytes_rejected():
    with pytest.raises(DocumentParseError):
        parse_document("resume.pdf", "application/pdf", b"")


def test_unsupported_type_rejected():
    content = b"some binary"
    with pytest.raises(DocumentParseError):
        parse_document("photo.png", "image/png", content)


def test_txt_supported():
    text = parse_document("job.txt", "text/plain", b"Python developer wanted")
    assert "Python developer wanted" in text


def test_scanned_pdf_without_text_raises():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    import io

    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(DocumentParseError):
        extract_pdf_text(buffer.getvalue())


def test_corrupt_pdf_with_magic_bytes():
    with pytest.raises(DocumentParseError):
        extract_pdf_text(b"%PDF-1.4 broken content \x00\xff")
