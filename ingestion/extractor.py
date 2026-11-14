"""Digital page text extraction using PyMuPDF.

Handles digital and mixed pages — no external API calls.
Scanned pages must be routed to the OCR module instead.
"""

from pathlib import Path

import pymupdf as fitz  # noqa: F401 (pymupdf provides the fitz namespace)


def extract_digital_page(pdf_path: str | Path, page_number: int) -> str:
    """Extract text from a single page using PyMuPDF's built-in text layer.

    Args:
        pdf_path:    Absolute or relative path to the source PDF.
        page_number: 1-indexed page number (matches human/PDF numbering).

    Returns:
        Extracted text string. May be empty for pages with no text layer.

    Raises:
        ValueError: if page_number is out of range for the document.
        FileNotFoundError: if the PDF does not exist.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with fitz.open(str(pdf_path)) as doc:
        total_pages = len(doc)
        if page_number < 1 or page_number > total_pages:
            raise ValueError(
                f"page_number {page_number} out of range (document has {total_pages} pages)"
            )
        # PyMuPDF is 0-indexed internally
        page = doc[page_number - 1]
        text = page.get_text("text")

    return text


def render_page_to_png_bytes(pdf_path: str | Path, page_number: int, dpi: int = 150) -> bytes:
    """Render a PDF page to PNG image bytes for OCR.

    Args:
        pdf_path:    Path to the source PDF.
        page_number: 1-indexed page number.
        dpi:         Rendering resolution. 150 DPI is a good balance of
                     OCR accuracy vs. token cost.

    Returns:
        PNG image bytes ready to send to a vision model.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with fitz.open(str(pdf_path)) as doc:
        total_pages = len(doc)
        if page_number < 1 or page_number > total_pages:
            raise ValueError(
                f"page_number {page_number} out of range (document has {total_pages} pages)"
            )
        page = doc[page_number - 1]
        zoom = dpi / 72  # 72 is PyMuPDF's base DPI
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")
