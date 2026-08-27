"""Resume/cover-letter export helpers (TXT, Markdown, PDF).

PDF generation reuses the project's dependency-free minimal PDF writer
(`services/pdf_parser.build_fake_pdf`), so no extra libraries are required.
"""

from __future__ import annotations

from app.services.pdf_parser import build_fake_pdf


def markdown_to_plain(markdown: str) -> str:
    """Lightweight MD -> readable text (headers underlined, bullets kept)."""
    out_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("### "):
            heading = stripped[4:]
            out_lines.extend([heading, "-" * len(heading)])
        elif stripped.startswith("## "):
            heading = stripped[3:]
            out_lines.extend(["", heading, "=" * len(heading)])
        elif stripped.startswith("# "):
            heading = stripped[2:]
            out_lines.extend([heading.upper(), "=" * len(heading)])
        else:
            out_lines.append(stripped.replace("**", ""))
    return "\n".join(out_lines)


def to_txt(content: str) -> bytes:
    """TXT export accepts plain text or markdown; markdown is flattened."""
    if content.lstrip().startswith("#"):
        content = markdown_to_plain(content)
    return content.encode("utf-8")


def to_markdown(content: str) -> bytes:
    return content.encode("utf-8")


def to_pdf(content: str) -> bytes:
    """Render text/markdown as a simple formatted PDF."""
    plain = markdown_to_plain(content)
    return build_fake_pdf(plain.splitlines(), max_lines_per_page=52)
