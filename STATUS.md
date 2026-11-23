# IRIS — Current Status

**Current stage:** Milestone 16 Complete (Curriculum Matrix Crawling & Test Isolation) — Checkpoint Saved  
**Current focus:** Ready for knowledge base expansion, production hardening, and continuous evaluation.

---

## 1. Executive Summary & Corpus Metrics

- **Discovered Institutional Documents:** **129 documents** in the catalogue across 5 active PEC web sources (Senate Meetings, Academic Calendars, Rules & Procedures, UG Curriculum Schemes, Training & Placement).
- **Ingested Knowledge Base:** **35 documents** durably stored in PostgreSQL.
- **Extracted & Cleaned Pages:** **1,125 pages** (digital PyMuPDF extraction + resumable Gemini Vision OCR).
- **Structure-Aware Chunks:** **894 chunks** with strict page provenance (`start_page`, `end_page`).
- **Vector Embeddings:** **894 / 894 chunks (100%)** embedded using `gemini-embedding-001` (768 dimensions) in `pgvector`.
- **Automated Test Coverage:**
  - **Backend:** 46/46 crawler tests passing, 138/138 RAG/auth/API tests passing.
  - **Frontend:** 60/60 Vitest tests passing across 4 suites.
  - **Database Isolation:** All pytest runs automatically execute in `iris_test_db` with zero dev database pollution.

---

## 2. Milestone Completion History (M0 — M16)

### Milestone 0: Environment, PostgreSQL + pgvector, Alembic Foundation
- Initialized Git repository with strict `.gitignore` excluding raw PDFs, intermediate data, environment secrets, and virtual environments.
- Created Python 3.14 virtual environment (`.venv`) and installed base dependencies (`sqlalchemy`, `alembic`, `pgvector`, `psycopg[binary]`, `python-dotenv`, `pydantic-settings`, `pytest`).
- Configured local Docker Compose container `iris-postgres` (`pgvector/pgvector:pg16`) on port `5433` with persistent volume `iris_pgdata`.
- Created Alembic migration `0001_enable_vector_extension.py` activating PostgreSQL `vector` extension.
- Verified database connectivity, L2 distance (`<->`), and cosine distance (`<=>`) queries with `tests/test_database.py` (4/4 passed).

### Milestone 1: PDF Discovery & Digital Inspection
- Implemented `ingestion/discovery.py` for input allowlist scanning and SHA-256 chunked hashing.
- Implemented `ingestion/pdf_inspector.py` for page-by-page digital text analysis, image counting, and classification (`predominantly_digital`, `predominantly_scanned`, `mixed`).
- Created CLI runner `inspect_corpus.py` and exported initial inventory report to `data/inventory_report.md`.
- Verified discovery, hash determinism, and PDF immutability in `tests/test_inspection.py` (8/8 passed).

### Milestone 2: Durable Page-Level Extraction & Gemini Vision OCR
- Applied Alembic migration `0002_create_documents_and_pages.py` (`documents` and `pages` tables with cascading foreign keys and unique `(document_id, page_number)` constraints).
- Implemented `database/repository.py` for idempotent document upserts and per-page transaction commits.
- Implemented `ingestion/extractor.py` using PyMuPDF for zero-API-cost digital page extraction and image rendering.
- Implemented thin Gemini OCR adapter in `ingestion/ocr.py` using `gemini-3.5-flash-lite` (primary) and `gemini-3.1-flash-lite` (fallback) with exponential backoff on 429 and verbatim transcription prompting (temperature 0).
- Built resumable orchestration pipeline in `ingestion/pipeline.py`.
- Verified extraction durability in `tests/test_extraction.py` (17/17 passed).

### Milestone 3: Conservative Cleaning & Metadata Classification
- Applied Alembic migration `0003_add_cleaned_text_to_pages.py` adding `cleaned_text` and `cleaning_version` to `pages`.
- Created `ingestion/cleaner.py`: Conservative text normalisation standardising unicode, whitespace, line-wrap hyphens, and bullet points while preserving Markdown tables, numbers, course codes, and dates.
- Created `ingestion/metadata_classifier.py` for deterministic document categorization (tagging category, academic year, version, and labels into `documents.metadata_`).
- Built audit runner `ingestion/clean_corpus.py` exporting `data/cleaning_report.md`.
- Verified cleaning and metadata integrity in `tests/test_cleaning.py`.

### Milestone 4: Structure-Aware Chunking
- Applied Alembic migration `0004_create_document_chunks.py` creating `document_chunks` table with `chunk_text`, `start_page`, `end_page`, `char_count`, `token_count`, `section_title`, and vector columns.
- Implemented `ingestion/chunker.py`: Structure-aware chunking algorithm splitting on Markdown headings, section markers, and paragraph boundaries while keeping Markdown tables intact and preserving strict page ranges.
- Built inspection runner `ingestion/chunk_corpus.py` generating `data/chunk_inspection.md`.
- Verified chunking and provenance in `tests/test_chunking.py` (6/6 passed).

### Milestone 5: Embedding Repository Foundations
- Implemented embedding repository functions in `database/repository.py` (`store_chunk_embedding`, `store_chunk_embeddings_batch`, `get_unembedded_chunks`, `get_chunk_embedding_status`).
- Added strict vector validation (768 dimensions, finite values, rejection of NaN/Inf).
- Verified repository transactions and rollbacks in `tests/test_embedding_repository.py`.

### Milestone 6: Gemini Embeddings Integration
- Implemented Gemini embedding provider in `embeddings/embedder.py` using `gemini-embedding-001` with 768 output dimensions.
- Configured task types: `RETRIEVAL_DOCUMENT` for chunks, `RETRIEVAL_QUERY` for user questions.
- Verified embedding generation, batching, and database persistence in `tests/test_embedding_provider.py`.

### Milestone 7: Semantic Retrieval & Grounding Evaluation
- Implemented semantic retrieval in `retrieval/retriever.py` with cosine distance (`<=>`) ordering and strict tie-breaking.
- Built retrieval CLI interface in `retrieval/search.py` supporting human-readable and JSON output.
- Built evaluation framework in `retrieval/evaluate.py` with 30 curated questions in `eval/retrieval_eval_dataset.json` (Hit@1: 88.0%, Hit@3: 96.0%, Hit@5: 100.0%, Negative rejection: 100.0%).
- Verified retrieval accuracy in `tests/test_retrieval.py` (14/14 passed).

### Milestone 8: Modular RAG Answer Engine
- Built modular RAG pipeline: `rag/context_builder.py`, `rag/evidence.py`, `rag/generator.py`, `rag/citation_validator.py`, `rag/pipeline.py`.
- Defined structured response statuses: `answered`, `clarification_needed`, `insufficient_evidence`, `handoff_recommended`.
- Security hardening: Prompt boundary tags (`<INSTITUTIONAL_DOCUMENT_CONTEXT>`) and anti-prompt injection defenses against adversarial text in documents.
- Built citation validator matching document filenames, page ranges, and section titles against retrieved evidence (zero fabricated citations).
- Evaluated on 36 curated benchmark questions: Status classification 86.1%, Citation existence 100%, Provenance 100%, Safe handoff accuracy 100%.
- Verified RAG engine in `tests/test_rag.py` (18/18 passed).

### Milestone 9: FastAPI Backend REST API
- Built FastAPI application (`api/main.py`) with modular routing, Pydantic schemas, dependency injection, and exception handlers.
- Endpoints: `POST /chat` (grounded RAG query), `GET /health` (liveness), `GET /health/ready` (readiness checking PostgreSQL and Gemini API).
- Safe error handling preventing leakage of stack traces, internal prompts, or database credentials.
- Configured CORS middleware for frontend communication.
- Verified API contracts in `tests/test_api.py` (17/17 passed).

### Milestone 10: React + TypeScript Frontend
- Built modern React + TypeScript frontend using Vite under `frontend/`.
- Minimalist academic visual identity with deep navy/slate palette, clear typography, and responsive layout.
- Suggested questions from PEC corpus (Cloud Computing, Deep Learning, Senate attendance regulations).
- API client (`frontend/src/services/api.ts`) connecting to `POST /chat` and `GET /health`.
- Renderers for `answered` (prose + verified citations), `clarification_needed` (amber prompt), and `handoff_recommended` (institutional office advisory).
- Multiline composer with Enter-to-send, Shift+Enter newline, and character limit feedback.
- Verified components in `frontend/src/test/` (36/36 passed).

### Milestone 11: Official Google OAuth 2.0 & Persistent Chat History
- Integrated official Google Identity Services OAuth 2.0 with backend token verification (`google-auth`).
- Enforced institutional domain restrictions (`ALLOWED_EMAIL_DOMAINS`, e.g. `@pec.edu.in`) and personal administrator allowlist (`ADMIN_EMAILS`).
- Implemented server-side opaque session token stored in `HttpOnly` signed cookies (`iris_session`) with SHA-256 token hashing in PostgreSQL.
- Applied Alembic migration `0005_add_auth_and_conversations.py` creating `users`, `sessions`, `conversations`, and `messages` tables.
- Built Conversation Sidebar with thread history, rename, delete, and real user badge.
- Security hardening: Fail-closed production settings, CSRF Origin validation, and mock button removal in production bundles.
- Verified backend auth tests (138/138 passed) and frontend tests (44/44 passed).

### Milestone 12: Curated Institutional PEC Web Crawler & Multi-Factor Change Detection
- Automated PEC web crawler (`PECCrawlerEngine` in `crawler/engine.py`) scanning official PEC domains without whole-PDF downloads.
- Domain security boundary enforcement (`is_pec_domain`).
- Configured 7 curated institutional sources in `crawler/config.py` (Senate Minutes, Academic Calendars, Rules & Procedures, UG Schemes, Training & Placement).
- Multi-factor change detection inspecting HTTP `ETag`, `Last-Modified`, and `Content-Length` headers alongside SHA-256 hashes.
- Applied Alembic migration `0006_add_crawler_tables.py` creating `crawler_sources`, `discovered_documents`, and `crawler_scans`.
- Added administrative endpoints: `POST /admin/crawler/scan`, `GET /admin/crawler/scans/latest`, `GET /admin/crawler/documents`.
- Verified crawler engine and security boundaries in `tests/test_crawler.py` (8/8 passed).

### Milestone 13: Human-in-the-Loop Document Approval, Rejection & Audit Logging
- Implemented lifecycle state machine: `discovered` -> `approved` | `rejected` -> `reconsider` -> `downloading` -> `ingested` | `download_failed` | `ingest_failed`.
- Applied Alembic migration `0007_add_crawler_approval_and_audit.py` creating the immutable `document_approval_audit` table.
- Applied Alembic migration `0008_add_crawler_scan_concurrency_index.py` for scan concurrency control.
- Administrative endpoints: `POST /admin/crawler/documents/{id}/approve`, `/reject`, `/reconsider`, and audit log retrieval `/history`.
- Row-level database locking (`with_for_update()`) preventing concurrent approval race conditions.
- Verified approval, rejection, and audit integrity in `tests/test_crawler_approval.py` (15/15 passed).

### Milestone 14: Approved Document Acquisition & Ingestion Pipeline
- Implemented `acquire_and_ingest_document` in `crawler/acquisition.py`.
- Applied Alembic migration `0009_add_crawler_ingestion_columns.py` linking `discovered_documents.ingested_document_id` to `documents.id`.
- PDF integrity validation (`verify_local_pdf`) checking magic bytes `%PDF-`, PyMuPDF parseability, and SHA-256 match before ingestion.
- Connected directly to IRIS pipeline: digital text extraction, Gemini OCR, text cleaning, chunking, and Gemini embeddings.
- Concurrency control: Global pipeline lock (`_PIPELINE_LOCK`) and document-level lock (`_ACTIVE_INGESTIONS_LOCK`).
- Acquisition endpoints: `POST /admin/crawler/documents/{id}/ingest`, `POST /admin/crawler/documents/{id}/retry`, and `GET /admin/crawler/documents/{id}/ingestion-status`.
- Crash recovery: `recover_stale_ingestions_on_startup` and `is_ingestion_active` automatically recovering orphaned downloading records across server crashes.
- Verified acquisition and retry in `tests/test_crawler_ingestion.py` (23/23 passed).

### Milestone 15: Primary Document Portal UI, Floating Mini Assistant & Chronological Sorting
- Reorganized administrator interface: Document Catalogue established as the **primary workspace** for logged-in administrators.
- Built floating quarter-size expandable Mini Chat Assistant (`MiniAssistant.tsx`) toggleable via floating action button for simultaneous catalogue management and RAG query verification.
- Horizontal filter toolbar: source filter, lifecycle status filter, change detection badges, search bar, and batch selection controls.
- Multi-directional chronological sorting: SQL-level and client-level sorting by `document_date` (parsing issued dates from Senate minutes like `18.01.2023`, `13.06.2022`, and academic years like `2023`, `2024`, `2025-26`).
- Verified UI components in `frontend/src/test/crawler.test.tsx` (10/10 passed).

### Milestone 16: Deep Matrix Curriculum Strategy & Automated Pytest Test Database Isolation
- Built `CurriculumStructureStrategy` (`crawler/strategies/curriculum.py`) capable of parsing multi-department tables (`https://pec.ac.in/programmes/ug/structure`) and following department landing subpages (`/structure/cse-ai-syllabus`, `/structure/cse-ds-syllabus`, etc.) to discover nested 2023/2024 degree schemes.
- Discovered and catalogued 22 additional discipline schemes (CSE 2023, CSE AI 2023, CSE DS 2023, Aerospace 2023, Civil 2024, ECE, VLSI 2024, Mech, Math & Computing 2024), expanding catalogue from 107 to **129 documents**.
- Automated Pytest database isolation in `tests/conftest.py`: Dynamically rebinds all test executions to `iris_test_db` with isolated pgvector extension and schemas.
- Cleaned up residual synthetic test records from the live development database (`iris_db`).
- Verified all crawler test suites passing: **46/46 passed**; all frontend tests passing: **60/60 passed**.

---

## 3. Database Schema & Alembic Migration History

| Version | Migration File | Purpose |
|---|---|---|
| **0001** | `0001_enable_vector_extension.py` | Enables PostgreSQL `vector` extension. |
| **0002** | `0002_create_documents_and_pages.py` | Creates `documents` and `pages` tables with cascading foreign keys. |
| **0003** | `0003_add_cleaned_text_to_pages.py` | Adds `cleaned_text` and `cleaning_version` to `pages`. |
| **0004** | `0004_create_document_chunks.py` | Creates `document_chunks` table with 768-dim `Vector` column. |
| **0005** | `0005_add_auth_and_conversations.py` | Creates `users`, `sessions`, `conversations`, and `messages` tables. |
| **0006** | `0006_add_crawler_tables.py` | Creates `crawler_sources`, `discovered_documents`, and `crawler_scans` tables. |
| **0007** | `0007_add_crawler_approval_and_audit.py` | Creates immutable `document_approval_audit` table and adds rejection reasons. |
| **0008** | `0008_add_crawler_scan_concurrency_index.py` | Adds partial index preventing concurrent running discovery scans. |
| **0009** | `0009_add_crawler_ingestion_columns.py` | Adds `local_filename`, `error_message`, and `ingested_document_id` foreign key. |

---

## 4. Current Ingested Corpus Details (35 Documents)

| Document Filename | Pages | Status | Extracted & Cleaned | Chunks & Embeddings |
|---|---|---|---|---|
| `Computer_Science_Engineering_DS_2023_Batch_Onwards.pdf` | 180 | Complete | 180/180 | 142 (768-dim) |
| `CSE_syllabus_24.pdf` | 174 | Complete | 174/174 | 151 (768-dim) |
| `UG Curriculum 2023 Vol 2.0.pdf` | 162 | Complete | 162/162 | 128 (768-dim) |
| `Computer_Science_Engineering_AI_2023_Batch_Onwards.pdf` | 156 | Complete | 156/156 | 120 (768-dim) |
| `Computer_Science_Engineering_DS_2022_Batch.pdf` | 83 | Complete | 83/83 | 64 (768-dim) |
| `Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf` | 55 | Complete | 55/55 | 53 (768-dim) |
| `Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf` | 47 | Complete | 47/47 | 53 (768-dim) |
| `UG Curriculum 2023 Vol. 1.0.pdf` | 43 | Complete | 43/43 | 32 (768-dim) |
| `grade ranges.pdf` | 35 | Complete | 35/35 | 24 (768-dim) |
| `Guidelines_for_Internship_Training_2021_Batch_Onwards.pdf` | 22 | Complete | 22/22 | 18 (768-dim) |
| `Placement_Internship_Policy_for_B_Tech_Session_2023-24.pdf` | 15 | Complete | 15/15 | 12 (768-dim) |
| `Placement_Internship_Policy_for_M_Tech_Session_2023-24.pdf` | 14 | Complete | 14/14 | 11 (768-dim) |
| `student_support_pec_ug_rules_2014_updated.pdf` | 14 | Complete | 14/14 | 10 (768-dim) |
| `Senate_Meeting_101_18_01_2023_-_Download_Minutes.pdf` | 9 | Complete | 9/9 | 8 (768-dim) |
| `Senate_Meeting_102_17_03_2023_-_Download_Minutes.pdf` | 10 | Complete | 10/10 | 8 (768-dim) |
| `Senate_Meeting_106_20_08_2024_-_Download_Minutes.pdf` | 10 | Complete | 10/10 | 8 (768-dim) |
| `Senate_Meeting_108_17_01_2025_-_Download_Minutes.pdf` | 10 | Complete | 10/10 | 8 (768-dim) |
| `Senate_Meeting_96_11_02_2022_-_Download_Minutes.pdf` | 8 | Complete | 8/8 | 7 (768-dim) |
| `Senate_Meeting_105_05_03_2024_-_Download_Minutes.pdf` | 8 | Complete | 8/8 | 7 (768-dim) |
| `Senate_Meeting_97_26_04_2022_-_Download_Minutes.pdf` | 7 | Complete | 7/7 | 6 (768-dim) |
| `MoM of Deans & HoDs,HoCs _16.09.2026.pdf` | 7 | Complete | 7/7 | 6 (768-dim) |
| `Senate_Meeting_103_04_08_2023_-_Download_Minutes.pdf` | 6 | Complete | 6/6 | 5 (768-dim) |
| `Senate_Meeting_104_11_10_2023_-_Download_Minutes.pdf` | 6 | Complete | 6/6 | 5 (768-dim) |
| `Senate_Meeting_109_14_05_2025_-_Download_Minutes.pdf` | 6 | Complete | 6/6 | 5 (768-dim) |
| `Senate_Meeting_99_19_07_2022_-_Download_Minutes.pdf` | 6 | Complete | 6/6 | 5 (768-dim) |
| `Guidelines for Mandatory Open Elective (OE) MOOCs.pdf` | 6 | Complete | 6/6 | 4 (768-dim) |
| `Senate_Meeting_107_11_10_2024_-_Download_Minutes.pdf` | 5 | Complete | 5/5 | 4 (768-dim) |
| `Academic_Calendar_for_26271_Semester.pdf` | 4 | Complete | 4/4 | 3 (768-dim) |
| `ION_Minutes of Deans Committee Meeting 23.11.2026.pdf` | 3 | Complete | 3/3 | 2 (768-dim) |
| `Minutes of the meeting of Dean Committee- 09.05.25.pdf` | 3 | Complete | 3/3 | 2 (768-dim) |
| `MoM_Deans & Heads Committee Mtg 17.12.25.pdf` | 3 | Complete | 3/3 | 2 (768-dim) |
| `Senate_Meeting_98_13_06_2022_-_Download_Minutes.pdf` | 3 | Complete | 3/3 | 2 (768-dim) |
| `Academic_Calendar_for_25262_Semester.pdf` | 2 | Complete | 2/2 | 2 (768-dim) |
| `Senate_Meeting_100_19_09_2022_-_Download_Minutes.pdf` | 2 | Complete | 2/2 | 2 (768-dim) |
| `MoM of Deans & Heads _24 June 2026.pdf` | 1 | Complete | 1/1 | 1 (768-dim) |
| **Total** | **1,125** | **100% Ingested** | **1,125 / 1,125** | **894 Chunks (100% Embedded)** |

---

## 5. Verified Test Suite Summary

- **Backend Pytest Suite:**
  - `pytest tests/test_crawler.py tests/test_crawler_approval.py tests/test_crawler_ingestion.py`: **46 / 46 passed (100%)**.
  - All tests execute strictly against `iris_test_db` via `tests/conftest.py`.
- **Frontend Vitest Suite:**
  - `vitest run --run`: **60 / 60 passed (100%)** across `src/test/api.test.ts`, `crawler.test.tsx`, `App.test.tsx`, and `components.test.tsx`.
- **Frontend Production Build:**
  - `npm run build` completes with 0 TypeScript and 0 Vite bundling errors.

---

## 6. Known System Constraints & Infrastructure

- **PostgreSQL + pgvector:** Bound to localhost port `5433` (`iris_db` for development, `iris_test_db` for testing).
- **External APIs:** Gemini models (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-embedding-001`) isolated in provider adapters.
- **Raw Document Immutability:** PDFs in `documents/` remain read-only.
- **Derived Artefacts:** All debug exports and inspection reports live in `data/` (ignored by Git).
