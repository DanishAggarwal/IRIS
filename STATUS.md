# IRIS — Current Status

**Current stage:** Milestone 4 Complete — Ready for Milestone 5/6  
**Current focus:** Vector embedding generation and incremental indexing.

## Completed
- [x] Project purpose and initial scope agreed.
- [x] Local-first architecture agreed.
- [x] React + TypeScript frontend and FastAPI backend selected.
- [x] Local PostgreSQL + pgvector selected.
- [x] Gemini selected as the initial OCR, embedding and generation provider.
- [x] Multi-agent orchestration, authentication, persistent chat history, Drive integration and cloud deployment deferred.
- [x] Prototype data policy set to public/student-wide documents manually selected by the user.
- [x] Anchor documentation prepared.
- [x] **Milestone 0 Completed:**
  - Initialized Git repository; verified `.gitignore` excludes `documents/`, `data/`, `.env`, and virtual environments.
  - Created Python virtual environment (`.venv`) using Windows Python 3.14.7.
  - Installed base dependencies (`sqlalchemy`, `alembic`, `pgvector`, `psycopg[binary]`, `python-dotenv`, `pydantic-settings`, `pytest`).
  - Configured and launched Docker Compose container `iris-postgres` (`pgvector/pgvector:pg16`) mapped to port `5433` with persistent volume `iris_pgdata`.
  - Configured `.env.example` and local `.env`.
  - Initialized database connection engine (`database/connection.py`) and Alembic migrations.
  - Created and applied migration `0001_enable_vector_extension.py` (`CREATE EXTENSION IF NOT EXISTS vector;`).
  - Verified database connectivity, extension activation, L2 distance (`<->`), and cosine distance (`<=>`) queries with `tests/test_database.py` (4 passed).
- [x] **Milestone 1 Completed:**
  - Added PyMuPDF (`pymupdf>=1.24.0`) to dependencies.
  - Implemented `ingestion/discovery.py` for allowlist scanning and SHA-256 chunked hashing.
  - Implemented `ingestion/pdf_inspector.py` for page-by-page digital text analysis, image counting, and classification.
  - Created CLI runner `inspect_corpus.py` and exported inventory report to `data/inventory_report.md`.
  - Created and ran `tests/test_inspection.py` verifying discovery, hash determinism, page counts, and source PDF immutability.
  - Total test suite: 8/8 passed.
- [x] **Milestone 2 Completed:**
  - Alembic migration `0002_create_documents_and_pages.py` applied: `documents` and `pages` tables with foreign keys, cascading deletes, unique constraints on `(document_id, page_number)`, and indexes on `(document_id, status)`.
  - SQLAlchemy ORM models created in `database/models.py` (`Document`, `Page`).
  - Database access repository created in `database/repository.py` with idempotent upserts, status tracking (`pending`, `success`, `failed`), and durable per-page commits.
  - PyMuPDF text extractor created in `ingestion/extractor.py` (`extract_digital_page`, `render_page_to_png_bytes`) with zero API cost for digital pages.
  - Thin Gemini OCR provider created in `ingestion/ocr.py` using `gemini-3.5-flash-lite` (primary) and `gemini-3.1-flash-lite` (fallback) with exponential backoff on 429, safe empty-page handling, and verbatim transcription prompting (temperature 0).
  - Ingestion orchestration pipeline created in `ingestion/pipeline.py` with automatic digital/scanned routing, hash deduplication, and crash-resilient per-page DB commits.
  - Unit and integration tests added in `tests/test_extraction.py` (mocked OCR, no quota burn).
  - Test suite: 17/17 passed.
  - **Full Corpus Extraction Results:**
    - `CSE_syllabus_24.pdf`: **174/174 pages extracted** (method: digital, 0 API calls).
    - `Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf`: **55/55 pages extracted** (method: gemini_ocr).
    - `Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf`: **47/47 pages extracted** (method: gemini_ocr).
    - Total corpus: **276 pages durably stored in PostgreSQL**.
- [x] **Milestone 3 Completed:**
  - Alembic migration `0003_add_cleaned_text_to_pages.py` applied: added `cleaned_text` and `cleaning_version` to `pages`.
  - Created `ingestion/cleaner.py`: conservative text normalisation that standardises unicode, anomalous whitespace, broken hyphenation across line-wraps, and bullet formats, while strictly preserving Markdown tables, numbers, course codes, dates, and paragraph breaks.
  - Created `ingestion/metadata_classifier.py`: deterministic, non-blocking document categorization tagging category (`syllabus`, `course_handout`), subcategories, academic year, version, and labels into `documents.metadata_`.
  - Created CLI runner `ingestion/clean_corpus.py` and exported audit report to `data/cleaning_report.md`.
  - Updated `ingestion/pipeline.py` to automatically clean newly ingested pages.
  - Unit and integration tests added in `tests/test_cleaning.py`.
  - **Full Corpus Cleaning Results:**
    - **276/276 pages cleaned** and updated in PostgreSQL without modifying raw `extracted_text`.
    - Total characters: 515,619 raw → 493,035 clean (4.38% reduction from whitespace/hyphen/footer normalisation).
- [x] **Milestone 4 Completed:**
  - Alembic migration `0004_create_document_chunks.py` applied: created `document_chunks` table with `id`, `document_id`, `chunk_index`, `chunk_text`, `start_page`, `end_page`, `char_count`, `token_count`, `section_title`, `metadata` (JSONB), `chunking_version`, `embedding` (Vector(768)), `embedding_model`, `embedding_dim`, and unique constraint on `(document_id, chunking_version, chunk_index)`.
  - SQLAlchemy ORM model `DocumentChunk` added to `database/models.py`.
  - Created `ingestion/chunker.py`: structure-aware chunking algorithm splitting on Markdown headings, uppercase section markers, and paragraph boundaries while keeping Markdown tables intact and maintaining strict page range provenance (`start_page`, `end_page`).
  - Created `ingestion/chunk_corpus.py` and generated inspection report at `data/chunk_inspection.md`.
  - Added 6 chunking and persistence tests in `tests/test_chunking.py`.
  - Total test suite: **35/35 passed**.
  - **Full Corpus Chunking Results:**
    - `Course Handout ... Ver 1_0.pdf`: **56 chunks** (avg: 595.1 tokens, 29 table chunks).
    - `Course Handout ... Ver 2_0.pdf`: **57 chunks** (avg: 573.7 tokens, 22 table chunks).
    - `CSE_syllabus_24.pdf`: **152 chunks** (avg: 477.5 tokens).
    - Total corpus: **257 structure-aware chunks durably persisted in PostgreSQL** (post-audit quality improvements: orphan heading headroom, HTML tables atomic).
- [x] **Milestone 5 Completed:**
  - Embedding database repository foundations created in `database/repository.py`.
  - Added unit and validation tests for 768-dim embeddings in `tests/test_embedding_repository.py`.
  - Added repository methods for incremental and batch embedding persistence and retrieval.
- [x] **Milestone 6 Completed:**
  - Gemini embedding integration created using `gemini-embedding-001` with 768 output dimensions.
  - Document task type: `RETRIEVAL_DOCUMENT`; Query task type: `RETRIEVAL_QUERY`.
  - Successfully embedded all 257 corpus chunks with 100% database persistence and zero null embeddings.
  - Added comprehensive provider and pipeline tests in `tests/test_embedding_provider.py`.
- [x] **Milestone 7 Completed:**
  - Semantic retrieval foundation implemented in `retrieval/retriever.py` with cosine distance (`<=>`) ordering and strict tie-breaking.
  - Created retrieval CLI interface in `retrieval/search.py` supporting human-readable and JSON output.
  - Built evaluation framework in `retrieval/evaluate.py` with 30 curated questions in `eval/retrieval_eval_dataset.json`.
  - Hit@1: 88.0%, Hit@3: 96.0%, Hit@5: 100.0%, Negative rejection: 100.0%.
  - Added unit and integration tests in `tests/test_retrieval.py` (14/14 passed).
- [x] **Milestone 8 Completed:**
  - Modular RAG answer engine implemented: `rag/models.py`, `rag/context_builder.py`, `rag/evidence.py`, `rag/generator.py`, `rag/citation_validator.py`, `rag/pipeline.py`, `rag/ask.py`, `rag/evaluate_rag.py`.
  - Structured enum status: `answered`, `clarification_needed`, `insufficient_evidence`, `handoff_recommended`.
  - Security hardening: boundary tags and anti-prompt injection defense against adversarial text in documents.
  - Strict citation validator matching document filenames, page ranges, and section titles against retrieved evidence.
  - Evaluated on 36 curated benchmark questions: Status classification 86.1% (31/36), Citation existence 100% (29/29), Citation provenance 100% (29/29), Claim-level support 100% (29/29), Safe handoff accuracy 100% (8/8).
  - Added unit and regression test suite in `tests/test_rag.py` (18/18 passed).
  - Total test suite: 93/93 passed.

## Current milestone
**M8 Completed — Merged into main**

## Corpus Chunk Summary in Database
| Document | Pages | Total Chunks | Avg Tokens | Multi-Page Chunks | Table Chunks | Embeddings |
|---|---|---|---|---|---|---|
| `Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf` | 55 | 53 | 623.5 | 45 | 29 | 53 (768-dim) |
| `Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf` | 47 | 53 | 611.8 | 36 | 22 | 53 (768-dim) |
| `CSE_syllabus_24.pdf` | 174 | 151 | 480.2 | 106 | 0 | 151 (768-dim) |
| **Total** | **276** | **257** | **536.8** | **187** | **51** | **257 (100%)** |

## Sample Corpus Inventory Report (from `data/inventory_report.md`)
| Filename | Size (KB) | Pages | Digital Pages | Mixed Pages | Scanned Pages | Overall Type | SHA-256 (first 12) |
|---|---|---|---|---|---|---|---|
| `CSE_syllabus_24.pdf` | 1415.0 | 174 | 169 | 5 | 0 | predominantly_digital | `d756848bf988...` |
| `Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf` | 3557.0 | 55 | 0 | 0 | 55 | predominantly_scanned | `2745da085829...` |
| `Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf` | 3234.1 | 47 | 0 | 0 | 47 | predominantly_scanned | `da765d44afb6...` |

**Key Takeaways:**
1. `CSE_syllabus_24.pdf` contains 174 pages of direct digital text that can be extracted directly without consuming OCR quota.
2. The two course handouts (Ver 1.0 and Ver 2.0) are scanned image PDFs (102 pages total across both), requiring page-by-page Gemini OCR and making them ideal test cases for resumable OCR and version discrepancy handling.

## Test Results from M0 & M1
- Command: `.venv\Scripts\pytest.exe -v`
  - `tests/test_database.py::test_database_connection` PASSED
  - `tests/test_database.py::test_vector_extension_active` PASSED
  - `tests/test_database.py::test_vector_insert_and_l2_distance_search` PASSED
  - `tests/test_database.py::test_vector_cosine_distance_search` PASSED
  - `tests/test_inspection.py::test_discover_pdfs_finds_all_sample_files` PASSED
  - `tests/test_inspection.py::test_sha256_hash_deterministic` PASSED
  - `tests/test_inspection.py::test_inspect_documents_extracts_pages_and_classifications` PASSED
  - `tests/test_inspection.py::test_source_pdfs_remain_unmodified` PASSED
  - Result: 8 passed in 6.14s.

## Pending decisions / verification
- [ ] Set up Gemini API key in `.env` for Milestone 2 OCR.
- [ ] Verify current Gemini vision/multimodal model name (e.g. `gemini-1.5-flash` or `gemini-2.5-flash`) for per-page transcription.
- [ ] Define the `pages` table schema in database models / Alembic migration to ensure OCR durability and resumability.

## Known constraints
- Port `5433` is used on localhost for Docker `pgvector` container.
- Original PDFs in `documents/` remain read-only.
- All derived reports live in `data/` (ignored by Git).
