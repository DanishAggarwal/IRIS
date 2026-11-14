# IRIS — Current Status

**Current stage:** Milestone 2 Complete — Ready for Milestone 3  
**Current focus:** Text cleaning, normalisation, and optional document metadata tagging.

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
  - Test suite: **17/17 passed**.
  - **Full Corpus Extraction Results:**
    - `CSE_syllabus_24.pdf`: **174/174 pages extracted** (method: digital, 0 API calls).
    - `Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf`: **55/55 pages extracted** (method: gemini_ocr).
    - `Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf`: **47/47 pages extracted** (method: gemini_ocr).
    - Total corpus: **276 pages durably stored in PostgreSQL**.
    - Interruption and resumption verified: successfully resumed incomplete pages without repeating completed pages.

## Current milestone
**M3 — Cleaning and optional metadata**

## Corpus Extraction Summary in Database
| Filename | Status | Total Pages | Extracted Pages | Extraction Method |
|---|---|---|---|---|
| `CSE_syllabus_24.pdf` | `complete` | 174 | 174 | `digital` |
| `Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf` | `complete` | 55 | 55 | `gemini_ocr` (`gemini-3.5-flash-lite`) |
| `Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf` | `complete` | 47 | 47 | `gemini_ocr` (`gemini-3.5-flash-lite`) |

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
