"""Tests for Milestone 2: page-level extraction and pipeline logic.

OCR calls are mocked — no live Gemini API calls are made in this suite.
"""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from database.connection import SessionLocal
from database.models import Document, Page
from database.repository import (
    get_document_by_hash,
    get_pending_pages,
    mark_page_success,
    upsert_document,
    upsert_page,
)
from ingestion.extractor import extract_digital_page, render_page_to_png_bytes

DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "documents"
CSE_SYLLABUS = DOCUMENTS_DIR / "CSE_syllabus_24.pdf"


# ---------------------------------------------------------------------------
# Extractor tests (no API calls)
# ---------------------------------------------------------------------------


def test_digital_extraction_returns_text():
    """extract_digital_page should return non-empty text from a known digital PDF."""
    if not CSE_SYLLABUS.exists():
        pytest.skip("CSE_syllabus_24.pdf not found in documents/ — skipping.")
    text = extract_digital_page(CSE_SYLLABUS, page_number=1)
    assert isinstance(text, str), "Expected a string return value."
    assert len(text) > 0, "Expected non-empty text from a digital page."


def test_digital_extraction_page_out_of_range():
    """extract_digital_page should raise ValueError for out-of-range page numbers."""
    if not CSE_SYLLABUS.exists():
        pytest.skip("CSE_syllabus_24.pdf not found in documents/ — skipping.")
    with pytest.raises(ValueError, match="out of range"):
        extract_digital_page(CSE_SYLLABUS, page_number=99999)


def test_render_page_to_png_returns_bytes():
    """render_page_to_png_bytes should return valid PNG bytes from a real PDF page."""
    if not CSE_SYLLABUS.exists():
        pytest.skip("CSE_syllabus_24.pdf not found in documents/ — skipping.")
    image_bytes = render_page_to_png_bytes(CSE_SYLLABUS, page_number=1)
    assert isinstance(image_bytes, bytes), "Expected bytes back."
    # PNG files start with the 8-byte PNG signature
    assert image_bytes[:4] == b"\x89PNG", "Expected PNG-format image bytes."


def test_source_pdf_unmodified_after_extraction():
    """Original PDF must have the same SHA-256 before and after extraction."""
    if not CSE_SYLLABUS.exists():
        pytest.skip("CSE_syllabus_24.pdf not found in documents/ — skipping.")
    import hashlib

    def sha256(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    before = sha256(CSE_SYLLABUS)
    extract_digital_page(CSE_SYLLABUS, page_number=1)
    render_page_to_png_bytes(CSE_SYLLABUS, page_number=1)
    after = sha256(CSE_SYLLABUS)
    assert before == after, "Source PDF was modified during extraction — this must never happen."


# ---------------------------------------------------------------------------
# Repository / resumability tests
# ---------------------------------------------------------------------------


def test_upsert_document_idempotent():
    """Upserting the same SHA-256 twice should update, not create a duplicate."""
    with SessionLocal() as session:
        sha256 = "test_sha256_idempotent_" + uuid.uuid4().hex[:8]
        doc1 = upsert_document(session, filename="test.pdf", sha256=sha256, status="pending")
        session.commit()
        doc1_id = doc1.id

        # Upsert again with same hash — should update, not duplicate
        doc2 = upsert_document(
            session, filename="test.pdf", sha256=sha256, status="extracting"
        )
        session.commit()

        assert doc2.id == doc1_id, "Second upsert must return the same document row."
        assert doc2.status == "extracting", "Status should be updated on second upsert."

        # Cleanup
        session.delete(doc2)
        session.commit()


def test_pipeline_skips_successful_pages():
    """get_pending_pages must exclude pages already marked success."""
    with SessionLocal() as session:
        sha256 = "test_sha256_resume_" + uuid.uuid4().hex[:8]
        doc = upsert_document(session, filename="resume_test.pdf", sha256=sha256)
        session.commit()

        # Seed pages 1-3 as pending
        for pnum in [1, 2, 3]:
            upsert_page(session, document_id=doc.id, page_number=pnum)
        session.commit()

        # Mark page 2 as success
        mark_page_success(
            session,
            document_id=doc.id,
            page_number=2,
            extracted_text="Some extracted text.",
            extraction_method="digital",
            extraction_model=None,
            extraction_version="ocr-v1",
        )
        session.commit()

        pending = get_pending_pages(session, doc.id)
        pending_numbers = [p.page_number for p in pending]

        assert 2 not in pending_numbers, "Successful page 2 must not appear in pending list."
        assert 1 in pending_numbers, "Page 1 (pending) should appear."
        assert 3 in pending_numbers, "Page 3 (pending) should appear."

        # Cleanup
        session.query(Page).filter(Page.document_id == doc.id).delete()
        session.delete(doc)
        session.commit()


# ---------------------------------------------------------------------------
# OCR module tests (mocked — no live API calls)
# ---------------------------------------------------------------------------


def test_ocr_extract_page_success(monkeypatch):
    """extract_page should return success dict when model call succeeds."""
    from ingestion import ocr

    mock_response = MagicMock()
    mock_response.text = "Transcribed text from page."

    with patch("ingestion.ocr._call_model", return_value="Transcribed text from page."):
        with patch("ingestion.ocr._configure_client"):
            result = ocr.extract_page(b"fake_image_bytes", page_number=1)

    assert result["status"] == "success"
    assert result["text"] == "Transcribed text from page."
    assert result["error"] is None


def test_ocr_extract_page_falls_back_on_primary_failure(monkeypatch):
    """When primary model fails repeatedly, extract_page should try fallback."""
    from ingestion import ocr

    call_count = {"n": 0}

    def fake_call_model(model_name, image_bytes):
        call_count["n"] += 1
        if "3.5" in model_name:
            raise Exception("429 rate limit exceeded")
        return "Fallback text."

    with patch("ingestion.ocr._call_model", side_effect=fake_call_model):
        with patch("ingestion.ocr._configure_client"):
            with patch("ingestion.ocr.time.sleep"):  # don't actually sleep
                result = ocr.extract_page(b"fake_image_bytes", page_number=1)

    assert result["status"] == "success"
    assert result["text"] == "Fallback text."
    assert "3.1" in result["model_used"]


def test_ocr_extract_page_fails_when_both_models_fail(monkeypatch):
    """When both models fail, extract_page should return a failed status."""
    from ingestion import ocr

    def always_fail(model_name, image_bytes):
        raise Exception("503 Service unavailable")

    with patch("ingestion.ocr._call_model", side_effect=always_fail):
        with patch("ingestion.ocr._configure_client"):
            with patch("ingestion.ocr.time.sleep"):
                result = ocr.extract_page(b"fake_image_bytes", page_number=1)

    assert result["status"] == "failed"
    assert result["text"] == ""
    assert result["error"] is not None
