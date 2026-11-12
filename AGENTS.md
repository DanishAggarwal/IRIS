# AGENTS.md — IRIS Agent Entry Point

You are assisting with IRIS, a local-first institutional-document RAG prototype.

## Before every task
1. Read `STATUS.md`.
2. Read `DEVELOPMENT_RULES.md`.
3. Read the relevant sections of `ARCHITECTURE_DECISIONS.md` and `MILESTONES_AND_MODULES.md`.
4. Work only on the current approved checkpoint.

## Hard constraints
- Prototype scope: single-agent RAG; no multi-agent framework, auth, user accounts, persistent chat history, Drive integration or cloud deployment yet.
- Stack: Python, FastAPI, React + TypeScript, local PostgreSQL + pgvector, Alembic, Gemini APIs initially.
- Raw input: `documents/` only. The user manually places public/student-wide PDFs there; treat it as the complete input allowlist.
- Never search outside `documents/` for source files. Never place or process internal, restricted or personal documents; keep them outside this workspace.
- Never send personal, restricted or internal documents or personal data to external APIs or coding agents.
- Never modify original PDFs.
- Preserve page-level provenance through extraction, chunks, retrieval and citations.
- OCR must be page-level, faithful, resumable and durable in the database.
- Use thin provider functions/classes; avoid elaborate abstraction frameworks.
- Keep ingestion repeatable and hash/configuration-aware.
- Use Alembic for schema changes.
- Do not fabricate citations or claim tests passed unless actually run.
- Do not change architecture, add major dependencies or move to later milestones without proposing it and receiving approval.

## Required task workflow
State the plan and files to change; implement one bounded checkpoint; run relevant tests; report exact results and limitations; wait for human review.

Detailed authority: `DEVELOPMENT_RULES.md`, `ARCHITECTURE_DECISIONS.md`, `MILESTONES_AND_MODULES.md`, `PROJECT_OVERVIEW.md`.
