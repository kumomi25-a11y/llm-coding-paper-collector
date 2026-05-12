"""Academic PDF text extraction using PyMuPDF4LLM."""

import logging
from pathlib import Path

logger = logging.getLogger("paper_collector")


def extract_pdf_text(pdf_path: str, min_text_length: int = 500) -> dict:
    """
    Extract text from an academic PDF, handling two-column layouts.

    Returns:
        {"text": str, "pages": int, "word_count": int, "method": str, "error": str|None}
    """
    path = Path(pdf_path)
    if not path.exists():
        return {"text": "", "pages": 0, "word_count": 0, "method": "none", "error": "File not found"}

    if path.stat().st_size < 1000:
        return {"text": "", "pages": 0, "word_count": 0, "method": "none", "error": "File too small (probable download error)"}

    # Strategy 1: PyMuPDF4LLM (handles two-column layouts)
    try:
        import pymupdf4llm

        md_text = pymupdf4llm.to_markdown(
            str(path),
            write_images=False,
            page_chunks=False,
        )
        word_count = len(md_text.split())

        if word_count >= min_text_length:
            return {
                "text": md_text,
                "pages": -1,  # pymupdf4llm doesn't return page count
                "word_count": word_count,
                "method": "pymupdf4llm",
                "error": None,
            }

        logger.warning(f"pymupdf4llm extracted only {word_count} words (below threshold), trying fallback")
    except Exception as e:
        logger.warning(f"pymupdf4llm failed: {e}")

    # Strategy 2: Plain PyMuPDF (fitz) with page-level text
    try:
        import fitz

        doc = fitz.open(str(path))
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text())
        doc.close()

        full_text = "\n\n".join(pages_text)
        word_count = len(full_text.split())

        if word_count >= min_text_length:
            return {
                "text": full_text,
                "pages": len(pages_text),
                "word_count": word_count,
                "method": "fitz_plain",
                "error": None,
            }

        logger.warning(f"fitz extracted only {word_count} words")

        # If text is short but non-zero, return it anyway
        if word_count > 0:
            return {
                "text": full_text,
                "pages": len(pages_text),
                "word_count": word_count,
                "method": "fitz_plain",
                "error": "Text may be incomplete (image-based PDF?)",
            }

    except Exception as e:
        logger.error(f"fitz failed: {e}")

    return {"text": "", "pages": 0, "word_count": 0, "method": "failed", "error": "All extraction methods failed"}
