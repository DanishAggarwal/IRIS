# IRIS — Current Status

**Current stage:** PEC Crawler Discovery, Approval & Acquisition Engine Complete — Checkpoint Saved
**Current focus:** Ready for next phase / evaluation.

## Completed
- [x] Project purpose and initial scope agreed.
- [x] Local-first architecture agreed.
- [x] React + TypeScript frontend and FastAPI backend selected.
- [x] Local PostgreSQL + pgvector selected.
- [x] Gemini selected as the initial OCR, embedding and generation provider.
- [x] Multi-agent orchestration, authentication, persistent chat history, Drive integration and cloud deployment deferred.
- [x] Prototype data policy set to public/student-wide documents manually selected by the user.
- [x] Anchor documentation prepared.
- [x] **Milestone 0–11 Completed.** (See Git history).
- [x] **PEC Crawler Discovery, Approval & Acquisition Engine Completed:**
  - Automated PEC web crawler (`PECCrawlerEngine`) scanning 7 curated institutional sources (Senate Minutes, Academic Calendars, Rules & Procedures, UG Curriculum Schemes & Handouts, Training & Placement Policies).
  - Multi-factor change detection tracking SHA-256 hashes, content lengths, HTTP ETag/Last-Modified headers, and detecting remote document updates.
  - Human-in-the-loop approval workflow with lifecycle statuses (`discovered`, `approved`, `rejected`, `downloading`, `ingested`, `download_failed`, `ingest_failed`) and immutable audit trails in `document_approval_audit`.
  - Resilient acquisition & ingestion pipeline (`acquire_and_ingest_document`) with PDF integrity validation, global pipeline concurrency locking, retry mechanisms, and crash recovery of orphaned operations across application restarts.
  - Chronological metadata sorting parsing issued dates and academic years from PEC document titles (e.g. Senate meetings and academic calendars) with multi-directional ordering.
  - Document Portal UI overhaul: Prominent co-primary management view for administrators with horizontal filter toolbar, batch approval/ingestion actions, and a floating quarter-size expandable mini chat assistant.
  - Pytest test database isolation via `tests/conftest.py` automatically routing test executions to a dedicated `iris_test_db` to ensure zero pollution of the live development database.
  - All automated test suites passing: 46/46 backend crawler tests, 60/60 frontend Vitest tests.
  - Current verified corpus: **129 authentic PEC catalogue documents** (including all 2023/2024 UG discipline schemes discovered via `CurriculumStructureStrategy`), **31 fully ingested PDFs**, **617 pages**, and **523/523 chunks 100% embedded in pgvector**.
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
- [x] **Milestone 9 Completed:**
  - FastAPI backend implemented with modular architecture: `api/main.py`, `api/config.py`, `api/schemas.py`, `api/dependencies.py`, `api/exceptions.py`, `api/routes/chat.py`, `api/routes/health.py`.
  - Endpoint `POST /chat` exposes grounded RAG pipeline with Pydantic request/response validation, whitespace stripping, top-k bounding (1–20), and strict public status mapping (`answered`, `clarification_needed`, `handoff_recommended`).
  - Liveness probe `GET /health` and non-quota burning readiness probe `GET /health/ready` verifying database connectivity and Gemini configuration.
  - Safe error handling (422, 503, 500) preventing leakage of stack traces, database credentials, or internal prompts.
  - Development CORS middleware configured for React frontend integration.
  - Added unit test suite in `tests/test_api.py` (17/17 passed).
  - Total test suite: **110/110 passed**.
- [x] **Milestone 10 Completed:**
  - Modern, responsive React + TypeScript frontend built with Vite under `frontend/`.
  - Minimalist academic visual identity with deep navy/slate palette, clear typography, generous whitespace, and restrained semantic statuses.
  - Welcome screen with PEC corpus-grounded suggested questions (Cloud Computing, Deep Learning, Senate attendance regulations).
  - Dedicated API service layer (`frontend/src/services/api.ts`) connecting to `POST /chat` and `GET /health` with safe error mapping.
  - Three public response status renderers: `answered` (safe markdown prose + verified citations), `clarification_needed` (amber continuation prompt), and `handoff_recommended` (institutional office recommendation + advisory disclaimer).
  - Citation component with document filenames, page ranges, section titles, and expandable grounded claim details (no fake URLs).
  - Multiline composer with Enter-to-send, Shift+Enter newline, and 1000-character limit feedback.
  - Real-time connection status badge (Connected, Disconnected, Checking).
  - Vitest + React Testing Library test suite in `frontend/src/test/`: **36/36 passed**.
  - Production build verified with `npm run build` (0 TypeScript / bundling errors).
- [x] **Milestone 11 Completed (Security Hardened & Ready for Merge Review):**
  - Added official Google Identity Services OAuth 2.0 with backend token verification (`google-auth`).
  - Configured institutional email domain allowlist (`ALLOWED_EMAIL_DOMAINS`, e.g. `pec.edu.in`) and personal administrator allowlist (`ADMIN_EMAILS`).
  - Implemented server-side opaque session token stored in `HttpOnly` cookie (`iris_session`) with SHA-256 token hashing in PostgreSQL.
  - Applied Alembic migration `0005_add_auth_and_conversations.py` creating `users`, `sessions`, `conversations`, and `messages` tables with cascading foreign keys and indexes. Added destructive downgrade safety docstring.
  - Verified corpus preservation: 3 documents, 276 pages, 257 chunks, and 257 768-dim embeddings remain 100% intact.
  - Implemented authenticated conversation CRUD endpoints (`/conversations`) with strict user ownership isolation.
  - Updated `POST /chat` with session authentication, CSRF origin verification, and automatic persistence of user questions, assistant answers, and verified citations.
  - **Security Fix Pass Applied:**
    - Critical C1: Mock authentication buttons guarded by `import.meta.env.DEV && !googleClientId`; verified completely eliminated in production bundles.
    - Critical C2: Default `APP_ENV` changed to `"production"` (fail-closed); mock tokens strictly rejected in non-development; mandatory `GOOGLE_CLIENT_ID` audience verification in development and production with safe error messages.
    - Critical C3: Local development standardized to `http://localhost:8000` and `http://localhost:5173` to ensure same-site cookie delivery with `SameSite=Lax`.
    - Important I1: Dynamic live `ADMIN_EMAILS` check in `require_admin` and automatic role synchronization/de-escalation in `get_current_user`.
    - Important I2: Verified Google email updates on `sub` match with cross-account collision prevention (409).
    - Additional: CSRF `Origin` validation on all state-changing cookie requests.
  - Full test verification: Backend pytest suite **138/138 passed** (100%); Frontend Vitest suite **44/44 passed** (100%).
  - End-to-end browser integration verification via Browser Agent: 12/12 steps verified (login, reload session persistence, Q&A synthesis, citations, thread sidebar, thread selection, and logout).
  - Frontend production build verified (`npm run build` clean in 1.12s).

## Current milestone
**M11 Completed (Hardened) — Ready for Commit & Merge Approval**

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
