# IRIS — Project Overview

**Project name:** IRIS (Information Retrieval and Intelligence System)  
**Project type:** Institutional document intelligence and question-answering system  
**Initial stage:** Local prototype using 5–10 public PDFs selected manually

## 1. What IRIS is

IRIS is a retrieval-augmented generation (RAG) application intended to help students, and eventually faculty, retrieve reliable information from institutional documents.

The document collection may contain academic regulations, examination rules, attendance policies, curriculum structures, course information, enrolment and registration procedures, forms, scholarships, administrative notices and other institutional material. The exact categories and structure are not fully known in advance.

Users ask questions in natural language. IRIS retrieves relevant passages from the source documents, constructs an answer grounded in those passages, and provides verifiable citations identifying the source document and page number.

IRIS must not invent institutional policy or answer every question regardless of available evidence. When documents do not provide sufficient support, it should clearly say so, ask a useful clarification where appropriate, or recommend contacting the relevant institutional office.

## 2. Core objectives

1. Make institutional PDFs searchable, including scanned documents.
2. Preserve provenance from original document and page through to every retrieved chunk and citation.
3. Support document categories that are not known in advance through optional, inspectable metadata inference.
4. Retrieve relevant evidence for natural-language questions.
5. Generate answers grounded in retrieved evidence rather than unsupported model knowledge.
6. Provide citations that resolve to real source documents and pages.
7. Handle uncertainty, outdated documents and conflicting evidence responsibly.
8. Support incremental ingestion of new and changed PDFs.
9. Keep the system modular enough to change OCR, embedding or generation providers.
10. Remain portable from local development to a future cloud deployment.

## 3. Initial scope

The first prototype uses approximately 5–10 representative PDFs placed in:

```text
iris/
├── documents/       # Public original PDFs selected for the prototype
└── ...
```

The `documents/` directory is the raw input directory. Original PDFs remain untouched. Derived data belongs under `data/`, which is separate from the raw input directory.

The prototype will implement:

- Local PDF discovery, hashing and inspection.
- Direct digital text extraction where usable text exists.
- Per-page Gemini-based processing for scanned pages, initially.
- Page-level persistence so OCR can resume and later stages can be rerun without repeating extraction.
- Conservative cleaning and page-aware metadata.
- Optional LLM-assisted document classification.
- Structure-aware, page-aware chunking.
- Gemini embeddings initially, with a deliberately selected vector dimension.
- Local PostgreSQL with pgvector.
- A single-agent RAG pipeline.
- Evidence-grounded answer generation, citations and abstention.
- A FastAPI backend and React + TypeScript frontend.

The first meaningful prototype is a repeatable pipeline that ingests the selected public sample PDFs, stores page text, chunks and embeddings, retrieves relevant passages with correct provenance, and answers questions with citations.

## 4. Data handling scope — public documents only

The prototype must ingest only documents that are already publicly available or explicitly shared with all students. The user will manually place the selected public PDFs in `documents/`; treat that folder as the complete input allowlist.

Use these data classes:

| Class | Examples | Prototype treatment |
|---|---|---|
| Public / student-wide | Published regulations, curriculum, handbooks, public notices and forms | Eligible for the prototype when manually selected by the user |
| Internal / limited | Internal circulars, purchase orders, finance records, staff correspondence | Excluded |
| Restricted / personal | Grade lists, marks, roll numbers linked to individuals, student records, IDs, personal correspondence, signatures or sensitive personal data | Excluded |
| Unknown | Anything whose public status is unclear | Excluded from the prototype |

Before placing a PDF in `documents/`, inspect the actual file and its pages. Do not include documents containing personal student information, internal material, signatures or sensitive details, even if they appear alongside public material. Do not copy entire mixed-content folders.

Do not send internal, restricted or unknown documents to Gemini, another external API, or an AI coding agent. Keep such files completely outside the project workspace, not merely outside the ingestion list.


## 5. Explicitly out of scope for the first prototype

- Multi-agent orchestration or separate academic, curriculum and enrolment agents.
- Google Drive integration; files are downloaded manually into `documents/`.
- Authentication and institutional Google OAuth.
- User accounts, roles and permissions.
- Persistent per-user conversation history and conversation management.
- Cloud hosting and managed cloud databases.
- Production background queues and distributed workers.
- A comprehensive taxonomy designed before inspecting the corpus.
- Ingestion of internal, restricted or unclassified documents.

The architecture should leave room for future features, but they must not delay the working prototype.

## 6. Intended user experience

A user should eventually be able to ask a natural-language question, receive a concise evidence-backed answer, inspect source-document/page citations, and understand when the available documents do not support a definitive answer.

The initial frontend can be simple. Clarity, provenance and answer reliability matter more than visual complexity.

## 7. Definition of success

The prototype is successful when:

- Only public PDFs manually placed in `documents/` are processed.
- Digital and scanned pages are extracted with page provenance.
- Per-page extraction is resumable after failure.
- OCR output is durably stored and does not need to be repeated for rechunking or re-embedding.
- Ingestion is repeatable: unchanged documents are skipped, new documents are added, and changed documents are safely replaced.
- Retrieval finds expected evidence on a measurable test set.
- Generated answers are supported by retrieved evidence.
- Citations resolve to actual documents and pages.
- The system abstains when evidence is insufficient and surfaces conflicts.
- The backend can be used by a simple React interface.
- Provider changes and future cloud deployment do not require redesigning the core responsibilities.

## 8. Guiding principle

**Build the knowledge base first, make retrieval trustworthy second, and make the application intelligent and polished third.**

Develop IRIS as small, independently testable components. Human review and acceptance are required at every checkpoint.
