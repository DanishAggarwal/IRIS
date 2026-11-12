# IRIS — Milestones and Workable Modules

This document defines the implementation sequence, module boundaries, deliverables and acceptance checks. Complete each milestone through small, reviewable checkpoints.

## 1. Initial project layout

```text
iris/
├── documents/                  # Public/student-wide PDFs manually selected by the user
├── data/
│   ├── extracted/               # Optional exports/debug artefacts
│   ├── processed/               # Cleaned/intermediate artefacts
│   └── failed/                  # Failure reports
├── ingestion/
│   ├── discovery.py             # PDF discovery and hashing
│   ├── pdf_inspector.py         # Page inspection and digital extraction
│   ├── extractor.py             # Page-level extraction orchestration
│   ├── ocr.py                   # Gemini page-processing adapter
│   ├── cleaner.py               # Conservative cleaning
│   ├── classifier.py            # Optional metadata inference
│   ├── chunker.py               # Structure-aware chunking
│   └── pipeline.py              # Ingestion orchestration
├── embeddings/
│   └── embedder.py              # Thin embedding provider functions
├── database/
│   ├── connection.py
│   ├── models.py
│   ├── repository.py
│   └── migrations/              # Alembic
├── retrieval/
│   └── search.py
├── rag/
│   ├── query_processor.py
│   ├── context_builder.py
│   ├── generator.py
│   └── validator.py
├── api/
│   ├── main.py
│   ├── routes/
│   └── schemas/
├── frontend/                    # React + TypeScript
├── evaluation/
│   ├── questions.json
│   └── run_evaluation.py
├── tests/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── AGENTS.md
├── STATUS.md
├── PROJECT_OVERVIEW.md
├── ARCHITECTURE_DECISIONS.md
├── DEVELOPMENT_RULES.md
└── MILESTONES_AND_MODULES.md
```

This is a target structure, not a demand to create every file immediately. Create modules as their milestones begin.

## 2. Module responsibilities

### Ingestion
Turns user-selected public original PDFs into durable, page-aware extracted text. It discovers files, detects changes, extracts digital text or invokes page-level OCR, and records processing status. It does not generate user answers or perform vector retrieval.

### Embeddings
Converts chunks and user queries into vectors using the configured model and correct task types. It validates vector dimensions and records model identity. It does not classify documents or generate answers.

### Database
Persists documents, pages, chunks and embeddings. It exposes safe repository functions. It does not contain OCR prompts or answer-generation logic.

### Retrieval
Finds candidate chunks and returns text, IDs, provenance, metadata and scores. Start with pgvector semantic search. Add keyword/hybrid retrieval only when evaluation justifies it.

### RAG
Builds context from retrieved evidence, generates an answer and validates evidence/citations/abstention. It does not invent citations or scatter ad hoc database queries through generation code.

### API
Validates requests, invokes application services and returns structured responses. It does not duplicate ingestion or RAG logic.

### Frontend
Presents chat, answers and source citations. It calls FastAPI and never accesses PostgreSQL or secret provider keys directly.

### Evaluation
Measures extraction quality, retrieval success, answer grounding, citation accuracy and abstention using fixed test questions and expected source pages.

## 3. Milestones

### M0 — Repository, environment, database and migrations

**Goal:** Establish reproducible local development.

Tasks:
- Create project directory and Git repository.
- Create `documents/`; the user manually places only public/student-wide sample PDFs there.
- Create Python virtual environment.
- Add `.gitignore` before adding PDFs; explicitly ignore `documents/`, `data/`, `.env`, virtual environments, caches and local database artefacts.
- Set up PostgreSQL + pgvector locally, preferably using Docker.
- Configure `.env` and `.env.example`.
- Set up SQLAlchemy and Alembic now, not later.
- Create the first Alembic migration to enable the vector extension (and verify extension availability).
- Verify Python database connection and a vector insert/query.
- Create `AGENTS.md` and `STATUS.md`.

Acceptance:
- Database connection works.
- A test vector can be stored and queried.
- Alembic can apply and report migrations.
- `.gitignore` prevents sample PDFs and local data from being staged.
- No internal, restricted or personal source files are in the workspace.

### M0.5 — Sample selection and evaluation questions

**Goal:** Establish a safe and measurable sample corpus before spending OCR/embedding quota.

Tasks:
- The user manually selects only public/student-wide sample PDFs and places them in `documents/`.
- Check the selected sample set for obvious personal, internal or restricted content before processing.
- Create 20–30 questions grounded in the chosen sample PDFs.
- For each answerable question, record expected document and page(s).
- Include approximately 5 unanswerable questions.
- Do not include personal student data in test questions.

Acceptance:
- The sample set contains only user-selected public/student-wide PDFs.
- The question set has expected evidence locations.
- Unanswerable questions are explicitly labelled.
- Do not call Gemini for files outside `documents/` or for any file that appears to contain personal, internal or restricted information.

### M1 — PDF discovery and inspection

**Goal:** Reliably discover and inspect PDFs in `documents/`.

Tasks:
- Enumerate PDFs.
- Calculate SHA-256 hashes.
- Record filenames, sizes and basic metadata.
- Inspect page count and extractable digital text per page.
- Identify pages likely to require OCR.
- Produce an inventory report.

Acceptance:
- All sample PDFs are discovered.
- Page counts are correct.
- Digital/scanned page detection is sensible.
- Original PDFs remain unchanged.

### M2 — Page-level extraction and resumable OCR

**Goal:** Produce faithful page-level text from digital and scanned pages.

Tasks:
- Extract usable digital text page by page with PyMuPDF.
- Render scanned pages individually with PyMuPDF.
- Send one page at a time to the Gemini processor; do not rely on whole-document model output for page boundaries.
- Use a verbatim-transcription prompt: preserve headings, paragraph order, clause numbers, dates, amounts and table values; output Markdown tables where feasible; mark unreadable content `[illegible]`; never guess or summarise.
- Use temperature 0 where supported by the selected model/API.
- Persist each page's text and status in the `pages` table.
- Track extraction provider/model/version, method, status and error details.
- Resume failed pages after quota/network errors without reprocessing successful pages.
- Handle batching/rate limits carefully without losing page-level progress.

Acceptance:
- Representative scanned and digital PDFs produce page-level text.
- Page numbers map to the actual PDF pages.
- Important values and tables are manually spot-checked against source pages.
- A simulated/interrupted failure resumes only incomplete pages.
- Successful page OCR is not repeated during later rechunking/re-embedding.

### M3 — Cleaning and optional metadata

**Goal:** Prepare extracted content without losing meaning.

Tasks:
- Normalise whitespace and line breaks conservatively.
- Identify repetitive headers/footers only where safe.
- Preserve headings, tables, dates, clauses and exceptions.
- Optionally infer document type/category/subcategory.
- Support multiple labels and `unclassified`.
- Keep classification non-blocking; failed classification must not stop ingestion.
- Avoid metadata filtering in retrieval at this stage.

Acceptance:
- Cleaned text is inspectable against raw page text.
- Important source details survive.
- Classification can be skipped or corrected.

### M4 — Structure-aware chunking

**Goal:** Create useful retrieval units with provenance.

Tasks:
- Split on headings, sections and paragraph boundaries.
- Begin with approximately 500–800 tokens and 75–100 tokens overlap where needed; tune against evaluation.
- Avoid breaking tables or important clauses unnecessarily.
- Attach document ID, chunk ID, page start/end and optional section/category metadata.
- Record chunking version/configuration.
- Produce a chunk inspection report.

Acceptance:
- Chunks remain coherent when read independently.
- Every chunk maps to a real source document and page range.
- No critical table/clause content is lost.

### M5 — Database schema and persistence

**Goal:** Persist documents, pages and chunks.

Tasks:
- Create Alembic migration(s) for `documents`, `pages` and `document_chunks`.
- `documents`: stable ID, filename, hash, page count, basic source metadata, metadata, status and pipeline config.
- `pages`: document ID, page number, extracted text, extraction method/provider/model/version, status and error.
- `document_chunks`: text, document ID, page range, metadata, embedding vector, `embedding_model`, `embedding_dim` and chunking version.
- Add uniqueness on `(document_id, page_number)` and appropriate stable chunk identity.
- Add foreign keys and useful indexes.
- Choose vector column/index dimension based on M0/M0.5 configuration. Start with 768 dimensions; evaluate 1536 before locking the production choice.
- Implement repository operations.

Acceptance:
- Records survive database round trips.
- Foreign keys and uniqueness work.
- Page and chunk provenance is preserved.
- Model and dimension metadata are stored with vectors.

### M6 — Embeddings and incremental ingestion

**Goal:** Index chunks and make re-ingestion safe.

Tasks:
- Verify current Gemini embedding model name and supported output dimensions.
- Start at 768 dimensions; compare with 1536 using the evaluation questions before finalising.
- Use the provider's correct document and query task types where supported.
- Batch requests within API limits.
- Store model name and dimension with each vector.
- Detect changes using source hash and processing configuration/version.
- Skip unchanged complete content.
- Add new documents.
- Reprocess changed documents.
- Re-embed chunks when embedding model/configuration changes.
- Use transactional replacement of affected chunks.
- Make deletion explicit.

Acceptance:
- Embeddings have consistent dimensions and model metadata.
- Re-running ingestion does not duplicate data.
- New documents are added without reprocessing unchanged files.
- Changed content is replaced safely.
- Changing embedding model triggers a controlled re-embedding path.

### M7 — Semantic retrieval with measurable evaluation

**Goal:** Retrieve expected evidence for known questions.

Tasks:
- Embed queries using the matching model and query task type.
- Run pgvector similarity search.
- Return top-k chunks with complete provenance and scores.
- Initially search broadly; do not require inferred category filters.
- Run the 20–30 question evaluation set created in M0.5.
- For each answerable question, check whether at least one expected document/page appears in the top 5.
- Record recall@5 (or equivalent expected-page hit rate), inspect misses and tune chunking/retrieval.

Acceptance:
- Report `expected-page hits / answerable questions` for top 5.
- Set an explicit target after measuring the baseline; aim for at least 80% on the small curated set before proceeding, while documenting sample-size limitations.
- Retrieval misses are inspected and classified (OCR, chunking, embedding or query issue).
- Retrieval output remains independently inspectable.

### M8 — Basic single-agent RAG

**Goal:** Generate evidence-grounded answers.

Tasks:
- Build context from retrieved chunks.
- Define strict grounding instructions.
- Integrate Gemini answer generation.
- Return structured answer, status and source chunk references.
- Keep generation separate from retrieval.
- Handle no-result and low-evidence cases.

Statuses:
- `answered`
- `clarification_needed`
- `insufficient_evidence`
- `handoff_recommended`

Acceptance:
- Direct answerable questions produce evidence-supported responses.
- No-result questions do not trigger invented policy.
- Handoff is represented distinctly from ordinary insufficient evidence.

### M9 — Reliability, citations and expanded evaluation

**Goal:** Validate trustworthiness.

Tasks:
- Resolve citations from retrieved records in backend code.
- Test exact document/page references.
- Add ambiguity, conflicting-source, outdated-document and multi-document cases to the evaluation set.
- Add abstention tests for unanswerable questions.
- Evaluate answer faithfulness, citation accuracy and abstention accuracy.
- Surface conflicting documents instead of silently choosing one.

Acceptance:
- No fabricated citations in the test set.
- Unanswerable cases abstain appropriately.
- Conflicting cases surface the conflict.
- Metrics and known limitations are recorded.

### M10 — FastAPI backend

**Goal:** Expose RAG through versioned HTTP endpoints.

Tasks:
- Create FastAPI application.
- Define request/response schemas.
- Add `/api/v1/chat` and `/api/v1/health`.
- Invoke existing RAG services rather than duplicating their logic.
- Add validation, error handling and API tests.
- Keep provider keys server-side.

Acceptance:
- API returns answer, status and valid citations.
- Invalid requests return structured errors.
- React requires no direct database or Gemini access.

Ingestion can remain a local CLI command for the prototype.

### M11 — React frontend

**Goal:** Provide a simple usable chat prototype.

Tasks:
- Create React + TypeScript app.
- Build chat view and message display.
- Connect to FastAPI.
- Render citations with document/page details.
- Show loading, error, clarification and abstention states.
- Keep interface simple and accessible.

Acceptance:
- User can ask a question through the website.
- Answer and citations render correctly.
- Error and non-answer statuses are understandable.
- No secret keys are exposed.

## 4. Future milestones — deferred

Only begin these after the prototype has reliable ingestion, retrieval and grounded answers:

- **Authentication/users:** institutional Google OAuth, backend token verification, user records and roles.
- **Conversation history:** conversations/messages tables, ownership enforcement and saved history.
- **Google Drive:** connector that feeds the existing ingestion pipeline.
- **Cloud deployment:** managed PostgreSQL + pgvector, object storage, containerised services, backups and monitoring.
- **Advanced retrieval:** hybrid search, reranking, query rewriting, filters when evaluation supports them.
- **Multi-agent orchestration:** only if a demonstrated requirement justifies it.
- **Restricted-document support:** only with institutional approval, data governance, identity and document-level access controls, and approved/local processing and generation.

## 5. Checkpoint method

Break each milestone into bounded tasks. For example, M2 can be split into:
1. Extract one digital PDF page.
2. Render one scanned page.
3. Test Gemini transcription on that page.
4. Define the common page output schema.
5. Persist one page and verify it.
6. Add resume/status handling.
7. Run the sample corpus and inspect output.

At each checkpoint, specify inputs, outputs, files to change and tests. Review real outputs before moving on.

## 6. First end-to-end prototype demonstration

With the initial user-selected public 5–10 PDFs:

1. Place the selected public files in `documents/`.
2. Run discovery and inspect the inventory.
3. Run page-level extraction and inspect representative pages.
4. Verify extraction can resume after interruption.
5. Inspect cleaned text and optional metadata.
6. Inspect chunks and page references.
7. Generate embeddings and store them in PostgreSQL.
8. Run the 20–30 retrieval questions and inspect top-5 expected-page hits.
9. Ask answerable questions and verify citations.
10. Ask unanswerable questions and verify abstention.
11. Add one public PDF and rerun ingestion; unchanged documents should be skipped.
