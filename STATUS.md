# IRIS — Current Status

**Current stage:** Pre-implementation / Milestone 0 not yet started  
**Current focus:** Prepare the local development environment and verify PostgreSQL + pgvector + Alembic.

## Completed
- [x] Project purpose and initial scope agreed.
- [x] Local-first architecture agreed.
- [x] React + TypeScript frontend and FastAPI backend selected.
- [x] Local PostgreSQL + pgvector selected.
- [x] Gemini selected as the initial OCR, embedding and generation provider, subject to current API capabilities, quotas and provider terms.
- [x] Multi-agent orchestration, authentication, persistent chat history, Drive integration and cloud deployment deferred.
- [x] Prototype data policy set to public/student-wide documents manually selected by the user.
- [x] Anchor documentation prepared.

## Current milestone
**M0 — Repository, environment, database and migrations**

## Next checkpoints
1. Ensure only manually selected public/student-wide PDFs are placed in `documents/`.
2. Create/verify `.gitignore` before adding PDFs; explicitly ignore `documents/`, `data/` and `.env`.
3. Initialise Git.
4. Create Python virtual environment.
5. Start local PostgreSQL + pgvector using Docker Compose (recommended); local PostgreSQL is an alternative.
6. Configure environment variables.
7. Set up SQLAlchemy and Alembic.
8. Create initial migration enabling/verifying pgvector.
9. Verify connection and a vector insert/search.

## Pending decisions / verification
- [ ] Verify current Gemini OCR/document-processing model/API and quotas.
- [ ] Verify current Gemini embedding model name, supported dimensions and task types.
- [ ] Compare 768 and 1536 embedding dimensions on the evaluation set before finalising.
- [ ] Create 20–30 retrieval questions with expected source pages, including about five unanswerable questions.

## Known constraints
- No authentication or persistent conversation history in the prototype.
- No multi-agent architecture.
- No cloud database or deployment yet.
- No internal, restricted, personal or unclassified documents in the workspace or external APIs.
- Do not process files outside `documents/`; do not send personal, restricted or internal material to external APIs.

Update this file at every accepted checkpoint. Record what changed, tests run, results, and the next task.
