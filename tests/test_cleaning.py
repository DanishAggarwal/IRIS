"""Tests for Milestone 3: conservative text cleaning and document metadata classification."""

import pytest

from ingestion.cleaner import (
    CLEANING_VERSION,
    clean_text,
    normalise_unicode,
    repair_line_break_hyphenation,
    normalise_bullets,
    is_table_row,
)
from ingestion.metadata_classifier import METADATA_VERSION, classify_document


# ---------------------------------------------------------------------------
# Cleaner Unit Tests
# ---------------------------------------------------------------------------


def test_whitespace_and_blank_line_normalisation():
    """Conservative cleaning should collapse 3+ newlines to 2 and trim spaces."""
    raw = "Heading One   \n\n\n\nParagraph with    extra   spaces.\n\n\nAnother paragraph."
    cleaned = clean_text(raw)
    assert "Heading One\n\nParagraph with extra spaces.\n\nAnother paragraph." == cleaned


def test_dehyphenation_repairs_split_words():
    """Hyphenated words split across lines should be rejoined."""
    raw = "The implemen-\ntation of the algo-\nrithm was successful."
    cleaned = repair_line_break_hyphenation(raw)
    assert "The implementation of the algorithm was successful." == cleaned


def test_dehyphenation_preserves_dates_and_codes():
    """Dates, code identifiers, and session ranges with hyphens must remain intact."""
    raw = "Academic session 2023-24 and course code CS-101."
    cleaned = repair_line_break_hyphenation(raw)
    assert "Academic session 2023-24 and course code CS-101." == cleaned


def test_markdown_tables_preserved():
    """Markdown table rows must keep pipe delimiters and row structure."""
    raw = (
        "| Course Code | Course Name | Credits |\n"
        "|---|---|---|\n"
        "| CS101 | Data Structures | 4 |\n"
        "| CS102 | Operating Systems | 4 |"
    )
    cleaned = clean_text(raw)
    assert "| Course Code | Course Name | Credits |" in cleaned
    assert "| CS101 | Data Structures | 4 |" in cleaned
    assert "| CS102 | Operating Systems | 4 |" in cleaned


def test_unicode_invisible_and_fancy_quotes_normalised():
    """Non-breaking spaces, zero-width chars, and fancy quotes should be normalised."""
    raw = "‘Hello’\u00a0world\u200b! “Institutional”\u00a0guidelines."
    cleaned = normalise_unicode(raw)
    assert "'Hello' world! \"Institutional\" guidelines." == cleaned


def test_bullets_normalised_to_markdown_hyphen():
    """Assorted unicode bullet glyphs should be normalised to standard '- '."""
    raw = "• Item one\n▪ Item two\n◦ Item three"
    cleaned = normalise_bullets(raw)
    assert "- Item one\n- Item two\n- Item three" == cleaned


def test_dates_percentages_and_numbers_preserved():
    """Critical numbers, dates, and percentages must survive cleaning untouched."""
    raw = (
        "PEC/CSE/25/836\n"
        "Dated: 04/08/2025\n"
        "Students must achieve at least 40% in Mid-Sem and 50% in End-Sem."
    )
    cleaned = clean_text(raw)
    assert "PEC/CSE/25/836" in cleaned
    assert "Dated: 04/08/2025" in cleaned
    assert "40%" in cleaned
    assert "50%" in cleaned


def test_strip_standalone_running_page_number():
    """Standalone page number footers/headers at extremities should be stripped."""
    raw = "Page 12 of 55\nCourse Syllabus for B.Tech CSE\nContent here.\nPage 12 of 55"
    cleaned = clean_text(raw, page_number=12)
    assert "Page 12 of 55" not in cleaned
    assert "Course Syllabus for B.Tech CSE" in cleaned
    assert "Content here." in cleaned


# ---------------------------------------------------------------------------
# Metadata Classification Tests
# ---------------------------------------------------------------------------


def test_classify_syllabus_document():
    """Syllabus PDF should be classified as 'syllabus' with CSE tags."""
    meta = classify_document(
        filename="CSE_syllabus_24.pdf",
        first_pages_text=["Programme Structure and Syllabi for B. Tech. Computer Science & Engineering 2023 batch onwards"],
    )
    assert meta["category"] == "syllabus"
    assert "curriculum" in meta["subcategories"]
    assert "cse" in meta["subcategories"]
    assert "undergraduate" in meta["subcategories"]
    assert meta["department"] == "Computer Science & Engineering"
    assert "syllabus" in meta["labels"]


def test_classify_course_handout_document():
    """Course handout with date and version in filename should be accurately parsed."""
    meta = classify_document(
        filename="Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf",
        first_pages_text=["PEC/CSE/25/836 Dated: 4/8/2025 Subject: Course handouts of all the courses of CSE department"],
    )
    assert meta["category"] == "course_handout"
    assert "cse" in meta["subcategories"]
    assert meta["version"] == "1.0"
    assert meta["effective_date"] == "04/08/2025"
    assert meta["department"] == "Computer Science & Engineering"


def test_classification_fallback_is_non_blocking():
    """Unrecognized or empty documents should default to unclassified without throwing."""
    meta = classify_document(filename="random_unknown_file.pdf", first_pages_text=[])
    assert meta["category"] == "unclassified"
    assert meta["labels"] == ["unclassified"]
    assert meta["metadata_version"] == METADATA_VERSION


# ---------------------------------------------------------------------------
# Database Durability & Clean Separation Test
# ---------------------------------------------------------------------------


def test_raw_extracted_text_remains_unchanged_after_cleaning():
    """Raw extracted_text in DB must not be altered when cleaned_text is updated."""
    from database.connection import SessionLocal
    from database.models import Page
    from database.repository import update_page_cleaned_text

    with SessionLocal() as session:
        # Find any existing page in DB
        page = session.query(Page).filter(Page.status == "success").first()
        if not page:
            pytest.skip("No successful page found in DB to test.")

        original_raw = page.extracted_text
        doc_id = page.document_id
        page_num = page.page_number

        test_clean = clean_text(original_raw, page_number=page_num)
        update_page_cleaned_text(
            session,
            document_id=doc_id,
            page_number=page_num,
            cleaned_text=test_clean,
            cleaning_version=CLEANING_VERSION,
        )
        session.commit()

        # Re-fetch from DB and verify
        reloaded = session.query(Page).filter(
            Page.document_id == doc_id, Page.page_number == page_num
        ).first()

        assert reloaded.extracted_text == original_raw, "Raw extracted_text was altered!"
        assert reloaded.cleaned_text == test_clean, "Cleaned text was not saved properly!"
        assert reloaded.cleaning_version == CLEANING_VERSION
