"""Tests for Milestone 4: structure-aware document chunking and database persistence."""

import uuid
import pytest

from ingestion.chunker import (
    CHUNKING_VERSION,
    StructuralBlock,
    chunk_document_pages,
    estimate_tokens,
    extract_structural_blocks,
)
from database.connection import SessionLocal
from database.models import Document, DocumentChunk
from database.repository import (
    count_chunks_for_document,
    get_chunks_for_document,
    replace_document_chunks,
    upsert_document,
)


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_estimate_tokens():
    """Token estimation should return proportional token counts."""
    text = "This is a simple test sentence for token estimation."
    tokens = estimate_tokens(text)
    assert 5 <= tokens <= 20
    assert estimate_tokens("") == 0


def test_extract_structural_blocks_identifies_tables_and_headings():
    """extract_structural_blocks should cleanly separate markdown tables and headings."""
    page_text = (
        "## Course Objectives\n\n"
        "The objective of this course is to learn operating systems.\n\n"
        "| Unit | Topic | Hours |\n"
        "|---|---|---|\n"
        "| 1 | Introduction | 6 |\n"
        "| 2 | Processes | 8 |\n\n"
        "Final paragraph describing labs."
    )
    blocks = extract_structural_blocks(page_number=1, page_text=page_text)
    assert len(blocks) >= 4

    # Heading block
    headings = [b for b in blocks if b.is_heading]
    assert len(headings) >= 1
    assert "Course Objectives" in headings[0].text

    # Table block
    tables = [b for b in blocks if b.is_table]
    assert len(tables) == 1
    assert "| Unit | Topic | Hours |" in tables[0].text
    assert "| 2 | Processes | 8 |" in tables[0].text


def test_chunking_maintains_page_provenance():
    """Every chunk must have start_page <= end_page matching source pages."""
    pages = [
        (1, "Page 1 content introductory section.\n\n" * 15),
        (2, "Page 2 content middle section with detailed text.\n\n" * 15),
        (3, "Page 3 concluding remarks and lab references.\n\n" * 15),
    ]
    chunks = chunk_document_pages(pages, target_max_tokens=250)
    assert len(chunks) > 1

    for c in chunks:
        assert 1 <= c.start_page <= 3
        assert 1 <= c.end_page <= 3
        assert c.start_page <= c.end_page
        assert c.chunk_text.strip() != ""
        assert c.token_count > 0


def test_table_integrity_preserved_in_chunk():
    """A markdown table within token limits must remain unified in a chunk."""
    table_text = (
        "| S.No | Component | Weightage |\n"
        "|---|---|---|\n"
        "| 1 | Mid Term Exam | 30% |\n"
        "| 2 | End Term Exam | 50% |\n"
        "| 3 | Assignments | 20% |"
    )
    pages = [(1, f"Evaluation details:\n\n{table_text}\n\nAdditional notes.")]
    chunks = chunk_document_pages(pages)

    table_chunks = [c for c in chunks if (c.metadata or {}).get("has_table")]
    assert len(table_chunks) >= 1
    assert "| Mid Term Exam | 30% |" in table_chunks[0].chunk_text
    assert "| End Term Exam | 50% |" in table_chunks[0].chunk_text


def test_chunk_token_limits_respected():
    """Chunks should respect target maximum tokens within structural tolerance."""
    long_page_text = "Standard paragraph describing institutional syllabus in detail. " * 80
    pages = [(1, long_page_text)]
    chunks = chunk_document_pages(pages, target_max_tokens=300, target_overlap_tokens=60)

    for c in chunks:
        # Target is 300 + 60 overlap with boundary tolerance
        assert c.token_count <= 400


# ---------------------------------------------------------------------------
# Database Persistence Tests
# ---------------------------------------------------------------------------


def test_database_chunks_persistence_and_replacement():
    """Chunks must persist in document_chunks table and replace cleanly on re-chunk."""
    with SessionLocal() as session:
        sha256 = "test_chunk_sha256_" + uuid.uuid4().hex[:8]
        doc = upsert_document(session, filename="test_chunk.pdf", sha256=sha256)
        session.commit()

        # Create test chunk payloads
        chunks_payload_1 = [
            {
                "chunk_index": 0,
                "chunk_text": "Chunk zero text",
                "start_page": 1,
                "end_page": 1,
                "char_count": 15,
                "token_count": 4,
                "section_title": "Intro",
                "metadata": {"has_table": False},
            },
            {
                "chunk_index": 1,
                "chunk_text": "Chunk one text",
                "start_page": 1,
                "end_page": 2,
                "char_count": 14,
                "token_count": 4,
                "section_title": "Details",
                "metadata": {"has_table": True},
            },
        ]

        # Insert chunks
        persisted = replace_document_chunks(
            session=session,
            document_id=doc.id,
            chunking_version=CHUNKING_VERSION,
            chunks_data=chunks_payload_1,
        )
        session.commit()

        assert len(persisted) == 2
        count = count_chunks_for_document(session, doc.id, CHUNKING_VERSION)
        assert count == 2

        # Fetch and verify fields
        fetched = get_chunks_for_document(session, doc.id, CHUNKING_VERSION)
        assert fetched[0].chunk_text == "Chunk zero text"
        assert fetched[0].start_page == 1
        assert fetched[0].end_page == 1
        assert fetched[1].chunk_text == "Chunk one text"
        assert fetched[1].start_page == 1
        assert fetched[1].end_page == 2
        assert fetched[1].metadata_ == {"has_table": True}

        # Replace with 1 chunk (re-chunking simulation)
        chunks_payload_2 = [
            {
                "chunk_index": 0,
                "chunk_text": "Single updated chunk",
                "start_page": 1,
                "end_page": 2,
                "char_count": 20,
                "token_count": 5,
                "section_title": "Unified",
                "metadata": {},
            }
        ]
        replace_document_chunks(
            session=session,
            document_id=doc.id,
            chunking_version=CHUNKING_VERSION,
            chunks_data=chunks_payload_2,
        )
        session.commit()

        count_after = count_chunks_for_document(session, doc.id, CHUNKING_VERSION)
        assert count_after == 1
        updated = get_chunks_for_document(session, doc.id, CHUNKING_VERSION)
        assert updated[0].chunk_text == "Single updated chunk"

        # Cleanup
        session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
        session.delete(doc)
        session.commit()


# ---------------------------------------------------------------------------
# Targeted Quality Audit Regression Tests
# ---------------------------------------------------------------------------


def test_orphan_heading_stays_with_body_under_headroom():
    """Heading (4 tokens) + body (~755 tokens) must remain together under 10% headroom."""
    heading_text = "Course Objectives:"
    # Generate ~755 tokens body text (~2870 chars)
    body_sentence = "To inculcate the application of Mechanics concepts in engineering and familiarize students with rigid body kinematics. "
    body_text = (body_sentence * 24).strip()  # approx 755 tokens

    pages = [(39, f"{heading_text}\n\n{body_text}")]
    chunks = chunk_document_pages(pages, target_max_tokens=750)

    # Must be exactly 1 chunk containing both the heading and body
    assert len(chunks) == 1, f"Expected 1 merged chunk, got {len(chunks)}"
    c = chunks[0]
    assert c.chunk_text.startswith("Course Objectives:")
    assert body_sentence.strip() in c.chunk_text
    assert 750 <= c.token_count <= 825
    assert c.start_page == 39
    assert c.end_page == 39


def test_html_table_recognition_atomicity_and_metadata():
    """HTML <table> tags (case-insensitive) must be atomic table blocks with has_table metadata."""
    html_table = (
        '<table border="1">\n'
        '  <tr><td><b>Course Outcome</b></td><td><b>PO1</b></td><td><b>PO2</b></td></tr>\n'
        '  <tr><td>CO1</td><td>3</td><td>2</td></tr>\n'
        '  <tr><td>CO2</td><td>2</td><td>3</td></tr>\n'
        '</table>'
    )
    pages = [(4, f"Introductory text.\n\n{html_table}\n\nConsequent text.")]
    chunks = chunk_document_pages(pages)

    table_chunks = [c for c in chunks if (c.metadata or {}).get("has_table")]
    assert len(table_chunks) >= 1
    assert '<table border="1">' in table_chunks[0].chunk_text
    assert '</table>' in table_chunks[0].chunk_text
    assert table_chunks[0].metadata.get("has_table") is True

    # Test uppercase <TABLE> tag recognition
    html_upper = '<TABLE><TR><TD>Upper Table</TD></TR></TABLE>'
    blocks = extract_structural_blocks(page_number=1, page_text=html_upper)
    assert len(blocks) == 1
    assert blocks[0].is_table is True


def test_exact_page_provenance_spans():
    """Chunk metadata must contain accurate, ordered, non-overlapping page_spans."""
    page1_text = "Content from page one describing introduction."
    page2_text = "Content from page two describing details and algorithms."
    pages = [(1, page1_text), (2, page2_text)]

    chunks = chunk_document_pages(pages, target_max_tokens=500)
    assert len(chunks) == 1
    c = chunks[0]

    spans = c.metadata.get("page_spans")
    assert isinstance(spans, list)
    assert len(spans) == 2

    # Check page 1 span
    s1 = spans[0]
    assert s1["page"] == 1
    assert s1["char_start"] == 0
    assert c.chunk_text[s1["char_start"]:s1["char_end"]] == page1_text

    # Check page 2 span
    s2 = spans[1]
    assert s2["page"] == 2
    assert s2["char_start"] > s1["char_end"]  # non-overlapping, separated by \n\n
    assert s2["char_end"] == len(c.chunk_text)
    assert c.chunk_text[s2["char_start"]:s2["char_end"]] == page2_text

    # Single-page chunk span check
    single_page_chunks = chunk_document_pages([(5, "Single page content.")])
    sp_spans = single_page_chunks[0].metadata.get("page_spans")
    assert len(sp_spans) == 1
    assert sp_spans[0]["page"] == 5
    assert sp_spans[0]["char_start"] == 0
    assert sp_spans[0]["char_end"] == len(single_page_chunks[0].chunk_text)
