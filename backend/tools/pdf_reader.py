import re
from collections import Counter
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from tools.logger import get_logger
from tools.tool_errors import ExtractionError, FileProcessingError

logger = get_logger(__name__)

MAX_PAGES = 50
HEAD_PAGES = 30
TAIL_PAGES = 5
TRUNCATED_MARKER = "\n\n[...TRUNCATED...]\n\n"
MIN_TEXT_RATIO = 0.1       # scanned if <10% of sampled pages have text
GARBLE_RATIO = 0.6         # printable-char ratio below this → garbled


def extract_pdf_text(filepath: str) -> str:
    """
    Extract clean, readable text from a PDF file.

    Handles: single/two-column layouts, Unicode, large PDFs (auto-truncated),
    repeating headers/footers, and equation placeholders.

    Args:
        filepath: Absolute path to the PDF file.

    Returns:
        Clean extracted text string.

    Raises:
        FileProcessingError: If the file does not exist or cannot be opened.
        ExtractionError: For password-protected, scanned, corrupted, or garbled PDFs.
    """
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileProcessingError(f"PDF file not found: {path}")

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        msg = str(e).lower()
        if "password" in msg or "encrypted" in msg:
            raise ExtractionError(
                "PDF is password protected. Please provide an unlocked PDF."
            ) from e
        raise FileProcessingError(f"PDF file is corrupted or invalid: {e}") from e

    if doc.page_count == 0:
        doc.close()
        raise ExtractionError("PDF has no pages.")

    if doc.needs_pass:
        doc.close()
        raise ExtractionError(
            "PDF is password protected. Please provide an unlocked PDF."
        )

    if _is_scanned_pdf(doc):
        doc.close()
        raise ExtractionError(
            "PDF appears to be scanned (image-only). Text extraction not possible."
        )

    pages_text = _extract_pages(doc)
    page_count = doc.page_count
    doc.close()

    pages_text = _strip_headers_footers(pages_text)
    full_text = "\n\n".join(p for p in pages_text if p.strip())
    full_text = _clean_extracted_text(full_text)

    if len(full_text.strip()) < 50:
        raise ExtractionError("Could not extract readable text from PDF.")

    if _is_text_garbled(full_text):
        raise ExtractionError(
            "Extracted text appears corrupted or unreadable. "
            "The PDF may contain encoding issues or unsupported character sets."
        )

    logger.info(
        "PDF extraction completed | file=%s | pages=%d | chars=%d",
        path.name, page_count, len(full_text),
    )
    return full_text


def _is_scanned_pdf(doc: fitz.Document) -> bool:
    """Return True if the majority of sampled pages have no extractable text."""
    if doc.page_count == 0:
        return True
    sample_size = min(doc.page_count, 10)
    text_pages = sum(1 for i in range(sample_size) if doc.load_page(i).get_text().strip())
    return (text_pages / sample_size) < MIN_TEXT_RATIO


def _extract_pages(doc: fitz.Document) -> list[str]:
    """
    Extract text page by page using lazy loading.

    For PDFs with more than MAX_PAGES pages, only the first HEAD_PAGES
    and last TAIL_PAGES are extracted, with a TRUNCATED_MARKER between them.

    Returns:
        List of per-page text strings.
    """
    total = doc.page_count
    if total <= MAX_PAGES:
        indices = list(range(total))
        truncated = False
    else:
        indices = list(range(HEAD_PAGES)) + list(range(total - TAIL_PAGES, total))
        truncated = True
        logger.info(
            "PDF has %d pages — extracting pages 1-%d and %d-%d",
            total, HEAD_PAGES, total - TAIL_PAGES + 1, total,
        )

    pages_text: list[str] = []
    for i in indices:
        page = doc.load_page(i)          # lazy: loads one page at a time
        text = page.get_text("text")     # reading-order text
        text = _replace_equations(text)
        if text.strip():
            pages_text.append(text.strip())

    if truncated and pages_text:
        insert_at = min(HEAD_PAGES, len(pages_text))
        pages_text.insert(insert_at, TRUNCATED_MARKER)

    return pages_text


def _replace_equations(text: str) -> str:
    """Replace lines dominated by special characters with [EQUATION]."""
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        non_alpha = sum(1 for c in stripped if not c.isalnum() and not c.isspace())
        ratio = non_alpha / max(len(stripped), 1)
        if ratio > 0.6 and len(stripped) > 5:
            result.append("[EQUATION]")
        else:
            result.append(line)
    return "\n".join(result)


def _strip_headers_footers(pages_text: list[str]) -> list[str]:
    """
    Remove repeating headers and footers.

    Checks the first 2 lines and last 2 lines of every page.
    Any line appearing on more than 50% of pages is treated as a header/footer
    and stripped from all pages.
    """
    if len(pages_text) < 3:
        return pages_text

    threshold = max(2, len(pages_text) * 0.5)

    first_lines: Counter[str] = Counter()
    last_lines: Counter[str] = Counter()

    for page in pages_text:
        lines = [l for l in page.split("\n") if l.strip()]
        for line in lines[:2]:
            first_lines[line.strip()] += 1
        for line in lines[-2:]:
            last_lines[line.strip()] += 1

    repeating_top = {l for l, c in first_lines.items() if c >= threshold and len(l) <= 120}
    repeating_bottom = {l for l, c in last_lines.items() if c >= threshold and len(l) <= 120}

    if repeating_top or repeating_bottom:
        logger.debug(
            "_strip_headers_footers: removing %d header patterns, %d footer patterns",
            len(repeating_top), len(repeating_bottom),
        )

    cleaned: list[str] = []
    for page in pages_text:
        lines = page.split("\n")
        result_lines: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped in repeating_top and i < 3:
                continue
            if stripped in repeating_bottom and i >= len(lines) - 3:
                continue
            result_lines.append(line)
        cleaned.append("\n".join(result_lines))

    return cleaned


def _clean_extracted_text(raw_text: str) -> str:
    """
    Normalise extracted text:
    - Remove non-printable / garbage characters
    - Collapse excessive whitespace and blank lines
    - Strip trailing whitespace per line
    """
    raw_text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u0080-\uFFFF]", "", raw_text)
    raw_text = re.sub(r"[ \t]{3,}", " ", raw_text)
    lines = [l.rstrip() for l in raw_text.split("\n")]
    raw_text = "\n".join(lines)
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
    return raw_text.strip()


def _is_text_garbled(text: str) -> bool:
    """
    Return True if the text appears corrupted or unreadable.

    Detects:
    - Excessive non-printable / non-ASCII bytes (binary junk)
    - Extremely low printable-character ratio
    - Near-zero word density (no real words found)
    """
    if not text:
        return True
    printable = sum(1 for c in text if c.isprintable() or c in ("\n", "\t", "\r"))
    if printable / len(text) < GARBLE_RATIO:
        return True
    # Word density: at least one ASCII word per 50 characters
    words = re.findall(r"[A-Za-z]{3,}", text)
    if len(text) > 200 and len(words) < len(text) / 50:
        return True
    return False


def get_pdf_metadata(filepath: str) -> dict[str, Any]:
    """
    Return basic metadata for a PDF without full text extraction.

    Returns:
        dict with keys: pages (int), title (str), author (str), is_scanned (bool).

    Raises:
        FileProcessingError: If file does not exist or cannot be opened.
    """
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileProcessingError(f"PDF file not found: {path}")

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        raise FileProcessingError(f"Cannot open PDF for metadata: {e}") from e

    meta = doc.metadata or {}
    scanned = _is_scanned_pdf(doc)
    pages = doc.page_count
    doc.close()

    return {
        "pages": pages,
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "is_scanned": scanned,
    }


if __name__ == "__main__":
    import sys

    test_path = "tests/sample.pdf"
    try:
        text = extract_pdf_text(test_path)
        assert len(text) > 100, "Extracted text too short"
        print(f"OK pdf_reader: extracted {len(text)} characters")
    except FileProcessingError:
        print(f"SKIP no sample at {test_path}")
    except ExtractionError as e:
        print(f"ExtractionError: {e}")

    try:
        extract_pdf_text("nonexistent_file_xyz.pdf")
    except FileProcessingError:
        print("OK pdf_reader: FileProcessingError handled correctly")
