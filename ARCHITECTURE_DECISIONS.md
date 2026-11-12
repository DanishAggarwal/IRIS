# IRIS — Architecture and Design Decisions

This document is the source of truth for current architectural choices. Record proposed changes here with their reason and impact; do not silently change the architecture.

## 1. High-level architecture

The initial system has four main parts:

1. **Document ingestion:** discovers local PDFs, extracts page content, cleans it, optionally classifies it, chunks it and generates embeddings.
2. **Knowledge store:** local PostgreSQL + pgvector stores document metadata, durable page extraction, chunks, provenance and embeddings.
3. **RAG backend:** FastAPI exposes query functionality. A single RAG pipeline handles query embedding, retrieval, context construction, answer generation and evidence validation.
4. **Frontend:** React + TypeScript provides the initial chat interface and displays answers and citations.

```text
iris/documents/ (public PDFs manually selected by the user)
          |
          v
Discovery + SHA-256 change detection
          |
          v
PDF inspection / direct text extraction / per-page Gemini OCR
          |
          v
Durable page records in PostgreSQL
          |
          v
Conservative cleaning + optional classification
          |
          v
Structure-aware chunking
          |
          v
Gemini embeddings (initially 768 dimensions; evaluate 1536)
          |
          v
PostgreSQL + pgvector
          |
          v
FastAPI -> single-agent RAG -> Gemini generation
          |
          v
Evidence validation -> answer/citations/abstention
          |
          v
React frontend
```

## 2. Technology decisions

| Area | Initial choice | Notes |
|---|---|---|
| Development environment | Antigravity, local workspace | Coding assistant, not runtime dependency |
| Language | Python | Ingestion, retrieval and backend |
| Frontend | React + TypeScript | Separate web application |
| Backend/API | FastAPI | REST API |
| Database | PostgreSQL + pgvector | Local; Docker Compose recommended for a repeatable setup |
| PDF inspection/digital extraction | PyMuPDF | Page inspection, rendering and text extraction |
| Scanned-page extraction | Gemini API | Initial provider; per-page and resumable |
| Embeddings | Gemini embedding API | Initial provider; task types and dimensions configured |
| Answer generation | Gemini initially | Provider isolated from RAG logic |
| ORM / data access | SQLAlchemy | Keep database operations structured |
| Schema migrations | Alembic | Set up in Milestone 0 |
| Version control | Git | Commit verified checkpoints |
| Local infrastructure | Docker Compose recommended for PostgreSQL + pgvector | Antigravity can create the configuration; Docker must be installed and running on the host. A local PostgreSQL installation is an alternative. |

Free API access, quotas, model names, supported dimensions and data-use terms can change. Verify current Google documentation before implementation. Do not assume free access is unlimited or suitable for confidential documents.

## 3. Data handling — mandatory

### 3.1 Prototype rule


Classes:

- **Public/student-wide:** published regulations, curriculum, handbooks, public notices and forms. Eligible when the user has manually selected the file for this public-only prototype.
- **Internal/limited:** purchase orders, finance records, internal circulars and staff correspondence. Excluded.
- **Restricted/personal:** grade lists, marks, roll numbers linked to individuals, student records, IDs, personal correspondence, signatures and similar personal data. Excluded.
- **Unknown:** excluded; only files clearly public or student-wide should be placed in the input folder.

The user should inspect candidate PDFs before placing them in the folder. A generally public document can contain sensitive appendices, names, signatures or handwritten annotations; do not include such files.

Do not put excluded documents anywhere inside the Antigravity workspace. Excluding a file from the ingestion script is not sufficient if the coding agent can still read it.

Do not search Google Drive or other locations for additional source files. Process only the PDFs the user manually places in `documents/`.

### 3.2 External API scope

For the prototype, the manually selected public documents may be sent to Gemini for OCR, embedding and answer generation, subject to current provider terms. Do not send personal or restricted material. User queries are also sent to the generation provider. Do not test with personal student details.

If restricted material is ever required, stop and design a separate institution-approved deployment with appropriate local/approved OCR, embeddings, generation and access controls. Local OCR and embeddings alone do not protect retrieved text if a cloud LLM receives it.

## 4. OCR and extraction design

### 4.1 Page-level processing

Use PyMuPDF to inspect the PDF and extract usable digital text page by page. For scanned/image-based pages, render the page to an image and send that page to the Gemini processor. Do not rely on a model's whole-document response to invent or infer page boundaries.

Each page is an independently tracked unit. Store page number, extracted text, extraction method/provider/model, status, errors and relevant processing version. A failure on one page must not force successful pages to be processed again.

### 4.2 Transcription prompt

The OCR instruction should request faithful transcription, not summarisation or interpretation:

- Transcribe visible content as written.
- Preserve headings, paragraphs, clause numbers, dates, amounts and identifiers exactly.
- Represent tables as Markdown tables where feasible.
- Preserve reading order.
- Mark unreadable text as `[illegible]`; do not guess.
- Do not correct, modernise, summarise or infer missing text.
- Return only the requested page's transcription and structured status.

Use deterministic generation settings, including temperature 0 where the selected API/model supports it. Validate the actual SDK/API parameter support before implementation.

### 4.3 Durable extraction output

Prefer a `pages` table so page text is durable and associated with the document record/hash. This allows rechunking or re-embedding without paying for OCR again.

Suggested fields include:
- `page_id`
- `document_id`
- `page_number`
- `extracted_text`
- `extraction_method`
- `extraction_model`
- `extraction_version`
- `status`
- `error_message`
- timestamps

Add a uniqueness constraint on `(document_id, page_number)`. Store successful pages independently and resume only missing/failed/stale pages.

### 4.4 Provider isolation

Use thin provider modules or small classes, not elaborate abstraction hierarchies. The rest of the application calls functions such as `extract_page(...)`, `embed_documents(...)`, `embed_query(...)` and `generate_answer(...)`; it should not call Gemini SDK methods directly.

This keeps future provider changes manageable without creating unnecessary framework code.

## 5. Embedding design

Initial candidate: Google's Gemini embedding API, with the current supported model name verified at implementation time.

- Start with **768 dimensions** to reduce storage and stay within common vector-index dimension constraints.
- Compare 768 against **1536 dimensions** using the project's retrieval evaluation set before treating the choice as final.
- Verify the chosen model supports the requested output dimension.
- Use the model's appropriate task types for document passages and search queries (for example, retrieval-document versus retrieval-query task types where supported).
- Store `embedding_model` and `embedding_dim` with each embedding/chunk record.
- Keep model and dimension in configuration, not hardcoded across modules.

The pgvector column/index configuration must match the selected dimension. If changing dimensions or models, plan a new column/table or a controlled backfill; do not mix incompatible vectors. Every chunk must be re-embedded for a new embedding model. Similarity scores and abstention thresholds are not directly comparable across models and must be reevaluated.

## 6. PostgreSQL schema direction

Initial logical tables:

### `documents`
One record per source PDF: stable ID, filename, content hash, page count, basic source metadata, inferred metadata, processing state and pipeline configuration/version.

### `pages`
One record per document page: page number, extracted text, extraction provider/model/version, extraction method, status and error information. Unique `(document_id, page_number)`.

### `document_chunks`
Chunk text, document foreign key, page start/end, section/category metadata, embedding vector, `embedding_model` and `embedding_dim`, chunking version/configuration and stable chunk identity.

Use foreign keys, uniqueness constraints and migrations. A chunk must always trace back to a document and page range.

Future user/conversation/message tables are deferred. The schema must not prevent adding them later, but do not implement them now.

## 7. Incremental ingestion

- Calculate SHA-256 for every input PDF.
- Compare file hash and relevant processing configuration with stored state.
- Skip documents whose source and processing configuration are unchanged and complete.
- Process new documents.
- Reprocess changed documents.
- Resume failed page extraction without reprocessing successful pages.
- Replace affected chunks transactionally when chunking or embedding changes.
- Retain durable page text so changing chunking or embedding does not require repeating OCR.
- Do not automatically delete indexed content because a file is temporarily absent; deletion must be explicit.

Track source hash, OCR provider/model/version, cleaning version, chunking version and embedding model/dimension. Changing one stage should invalidate only the necessary downstream stages.

## 8. Classification and metadata

Document classification is optional and non-blocking in the prototype. Do not let classification failure prevent extraction, chunking or indexing.

Use inferred categories as descriptive metadata. Do not make metadata filters mandatory in initial retrieval. First evaluate broad retrieval; introduce filters only when the test set demonstrates that they improve results without excluding correct evidence.

Support multiple labels and `unclassified`. Inferred labels are fallible and must be inspectable.

## 9. RAG design and response statuses

Start with one RAG pipeline:

```text
User query
   -> query embedding
   -> pgvector retrieval
   -> structured chunks with provenance
   -> context construction
   -> Gemini answer generation
   -> evidence and citation validation
   -> structured response
```

No master agent or specialised agents in the prototype.

Response status values:

- `answered`: sufficient evidence supports an answer.
- `clarification_needed`: the user's question is materially ambiguous and clarification could resolve it.
- `insufficient_evidence`: the approved knowledge base does not contain enough evidence.
- `handoff_recommended`: the matter requires confirmation/action by an institutional office or human authority.

Citations must be resolved by backend code from actual retrieved records. A similarity score alone is not evidence that the answer is correct. Surface conflicting or outdated sources rather than silently choosing one.

## 10. API, frontend and future identity

React communicates with FastAPI through versioned endpoints. It never connects directly to PostgreSQL or calls Gemini with secret keys.

Authentication, user records and persistent conversation history are deferred. Keep the RAG service independent of identity. When those features are later introduced, add authenticated user context at the API/service boundary and enforce conversation ownership in backend database queries.

The initial prototype may use a single temporary conversation/session. Do not build a full conversation persistence system now.

## 11. Local-first, cloud-ready design

Develop locally first. Use local PostgreSQL + pgvector, preferably through Docker. Keep database URLs, model names, API keys, storage paths and environment settings configurable.

Set up Alembic from Milestone 0. Use migrations for every schema change. Keep database access in a repository/data-access layer and document storage behind a small storage interface where useful.

Future options include managed PostgreSQL with pgvector, object storage for PDFs, containerised React/FastAPI services and background workers. These are future deployment decisions, not current requirements.
