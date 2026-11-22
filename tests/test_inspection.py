"""Tests for PDF discovery, SHA-256 hashing, and page extractability inspection."""

from pathlib import Path
import pytest
from ingestion.discovery import discover_pdfs, compute_sha256
from ingestion.pdf_inspector import inspect_all_documents, inspect_pdf


def test_discover_pdfs_finds_all_sample_files():
    """Verify that all sample PDFs in documents/ are discovered and hashed."""
    docs = discover_pdfs("documents")
    assert len(docs) >= 3, f"Expected at least 3 PDFs, found {len(docs)}"
    
    filenames = [d.filename for d in docs]
    assert "Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf" in filenames
    assert "Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf" in filenames
    assert "CSE_syllabus_24.pdf" in filenames

    for doc in docs:
        assert len(doc.sha256) == 64
        assert doc.file_size_bytes > 0
        assert doc.path.exists()


def test_sha256_hash_deterministic():
    """Verify that computing SHA-256 twice on the same file produces identical hashes."""
    docs = discover_pdfs("documents")
    first_doc = docs[0]
    hash_again = compute_sha256(first_doc.path)
    assert first_doc.sha256 == hash_again


def test_inspect_documents_extracts_pages_and_classifications():
    """Verify page counting and digital/scanned classification for each document."""
    inspections = inspect_all_documents("documents")
    assert len(inspections) >= 3

    for item in inspections:
        assert item.total_pages > 0
        assert len(item.pages) == item.total_pages
        # Verify page numbers match index + 1
        for idx, page in enumerate(item.pages):
            assert page.page_number == idx + 1
            assert page.classification in ("digital", "scanned", "mixed", "empty")
            if page.char_count > 0:
                assert len(page.sample_text) > 0


def test_source_pdfs_remain_unmodified():
    """Verify that original PDFs are never modified during discovery and inspection."""
    docs_before = discover_pdfs("documents")
    hashes_before = {d.filename: d.sha256 for d in docs_before}
    sizes_before = {d.filename: d.file_size_bytes for d in docs_before}
    
    # Run full inspection
    _ = inspect_all_documents("documents")

    docs_after = discover_pdfs("documents")
    hashes_after = {d.filename: d.sha256 for d in docs_after}
    sizes_after = {d.filename: d.file_size_bytes for d in docs_after}

    assert hashes_before == hashes_after
    assert sizes_before == sizes_after
