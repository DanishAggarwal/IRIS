"""PDF inspection and page-level extractability analysis using PyMuPDF.

Preserves original PDFs as strictly read-only inputs.
Inspects page count, extractable digital text, embedded images, and classifies pages.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import pymupdf as fitz

from ingestion.discovery import DiscoveredPDF, discover_pdfs


@dataclass
class PageInspection:
    """Inspection details for a single PDF page."""
    page_number: int  # 1-indexed
    char_count: int
    word_count: int
    image_count: int
    drawing_count: int
    has_digital_text: bool
    classification: str  # "digital", "scanned", "mixed", "empty"
    sample_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "image_count": self.image_count,
            "drawing_count": self.drawing_count,
            "has_digital_text": self.has_digital_text,
            "classification": self.classification,
            "sample_text": self.sample_text,
        }


@dataclass
class DocumentInspection:
    """Complete inspection summary for a document."""
    discovered: DiscoveredPDF
    total_pages: int
    metadata: Dict[str, Any]
    pages: List[PageInspection]
    digital_page_count: int
    scanned_page_count: int
    mixed_page_count: int
    empty_page_count: int
    overall_type: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "discovered": self.discovered.to_dict(),
            "total_pages": self.total_pages,
            "metadata": self.metadata,
            "pages": [p.to_dict() for p in self.pages],
            "digital_page_count": self.digital_page_count,
            "scanned_page_count": self.scanned_page_count,
            "mixed_page_count": self.mixed_page_count,
            "empty_page_count": self.empty_page_count,
            "overall_type": self.overall_type,
        }


def inspect_page(page: fitz.Page, page_number: int) -> PageInspection:
    """Inspect a single page for extractable digital text and visual artifacts."""
    text = page.get_text("text").strip()
    char_count = len(text)
    words = text.split()
    word_count = len(words)
    images = page.get_images()
    image_count = len(images)
    drawings = page.get_drawings()
    drawing_count = len(drawings)

    # Classification logic:
    # - Scanned: very low character count (< 50 chars) but has images
    # - Digital: reasonable text (>= 50 chars) and no images
    # - Mixed: reasonable text and contains images/diagrams
    # - Empty: zero text and zero images
    if char_count == 0 and image_count == 0:
        classification = "empty"
        has_digital_text = False
    elif char_count < 50 and image_count > 0:
        classification = "scanned"
        has_digital_text = False
    elif char_count >= 50 and image_count > 0:
        classification = "mixed"
        has_digital_text = True
    else:
        classification = "digital"
        has_digital_text = True

    sample_preview = " ".join(text[:120].split())

    return PageInspection(
        page_number=page_number,
        char_count=char_count,
        word_count=word_count,
        image_count=image_count,
        drawing_count=drawing_count,
        has_digital_text=has_digital_text,
        classification=classification,
        sample_text=sample_preview,
    )


def inspect_pdf(pdf_entry: DiscoveredPDF) -> DocumentInspection:
    """Open and inspect a PDF file without modifying it."""
    doc = fitz.open(pdf_entry.path)
    try:
        total_pages = len(doc)
        meta = doc.metadata or {}
        sanitized_meta = {
            "title": meta.get("title") or "",
            "author": meta.get("author") or "",
            "subject": meta.get("subject") or "",
            "creator": meta.get("creator") or "",
            "producer": meta.get("producer") or "",
            "creation_date": meta.get("creationDate") or "",
        }

        pages: List[PageInspection] = []
        digital_count = 0
        scanned_count = 0
        mixed_count = 0
        empty_count = 0

        for i, page in enumerate(doc):
            p_inspect = inspect_page(page, page_number=i + 1)
            pages.append(p_inspect)
            if p_inspect.classification == "digital":
                digital_count += 1
            elif p_inspect.classification == "scanned":
                scanned_count += 1
            elif p_inspect.classification == "mixed":
                mixed_count += 1
            else:
                empty_count += 1

        if scanned_count > (total_pages / 2):
            overall_type = "predominantly_scanned"
        elif digital_count > (total_pages / 2):
            overall_type = "predominantly_digital"
        else:
            overall_type = "mixed"

        return DocumentInspection(
            discovered=pdf_entry,
            total_pages=total_pages,
            metadata=sanitized_meta,
            pages=pages,
            digital_page_count=digital_count,
            scanned_page_count=scanned_count,
            mixed_page_count=mixed_count,
            empty_page_count=empty_count,
            overall_type=overall_type,
        )
    finally:
        doc.close()


def inspect_all_documents(source_dir: Path | str = "documents") -> List[DocumentInspection]:
    """Discover and inspect all PDFs in the source directory."""
    discovered = discover_pdfs(source_dir)
    return [inspect_pdf(doc) for doc in discovered]


def generate_inventory_report(inspections: List[DocumentInspection]) -> str:
    """Generate a clean Markdown inventory report."""
    lines = [
        "# IRIS Document Inventory Report",
        "",
        f"**Total Documents Discovered:** {len(inspections)}",
        "",
        "| Filename | Size (KB) | Pages | Digital Pages | Mixed Pages | Scanned Pages | Overall Type | SHA-256 (first 12) |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for item in inspections:
        kb_size = f"{item.discovered.file_size_bytes / 1024:.1f}"
        short_hash = f"`{item.discovered.sha256[:12]}...`"
        lines.append(
            f"| `{item.discovered.filename}` | {kb_size} | {item.total_pages} | "
            f"{item.digital_page_count} | {item.mixed_page_count} | {item.scanned_page_count} | "
            f"{item.overall_type} | {short_hash} |"
        )

    lines.append("")
    lines.append("## Detailed Document Summaries")
    lines.append("")

    for item in inspections:
        lines.append(f"### {item.discovered.filename}")
        lines.append(f"- **Path:** `{item.discovered.relative_path}`")
        lines.append(f"- **SHA-256:** `{item.discovered.sha256}`")
        lines.append(f"- **Total Pages:** {item.total_pages}")
        lines.append(f"- **Digital / Mixed / Scanned / Empty:** {item.digital_page_count} / {item.mixed_page_count} / {item.scanned_page_count} / {item.empty_page_count}")
        lines.append(f"- **Classification:** {item.overall_type}")
        if item.metadata.get("title"):
            lines.append(f"- **Metadata Title:** {item.metadata['title']}")
        if item.metadata.get("author"):
            lines.append(f"- **Metadata Author:** {item.metadata['author']}")
        lines.append("")

    return "\n".join(lines)
