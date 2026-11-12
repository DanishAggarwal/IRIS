# IRIS — Strict Development Rules

These rules apply to all contributors and coding agents, including Antigravity/Gemini.

## 1. Scope discipline

1. Build the agreed single-agent RAG prototype first.
2. Do not introduce multi-agent orchestration, LangGraph, a separate vector database, Redis, Celery, Kubernetes or other infrastructure without an approved concrete requirement.
3. Do not implement authentication, user management or persistent conversation history in the current prototype.
4. Do not implement Google Drive integration in the current prototype.
5. Do not build a large frontend before ingestion and retrieval work.
6. Do not add dependencies merely because they are popular in RAG tutorials.
7. Prefer the simplest implementation that meets the current milestone.

## 2. Data confidentiality — non-negotiable

1. The user manually selects public/student-wide PDFs and places them in `documents/`. Treat that directory as the complete input allowlist; process nothing from outside it.
2. Internal, restricted, personal or unknown documents must never be placed in `documents/`, `data/`, or anywhere inside the Antigravity workspace.
3. Examples of excluded material include grade/marks lists, roll numbers linked to individuals, student records, IDs, purchase orders, finance records, internal correspondence and documents with signatures or personal details.
4. The user is responsible for checking candidate PDFs before placing them in `documents/`. Do not assume a document is safe based on its filename or general category; if a file visibly contains personal or restricted material, stop and flag it.
5. Do not search for or access documents outside `documents/`. Do not send personal, restricted or internal material to Gemini, another external API or an AI coding agent.
6. Do not test with real personal student questions or identifiers.
7. Do not rely on `.gitignore` as a confidentiality control. It prevents accidental commits; it does not prevent local tools or agents from reading files.
8. If a file appears to contain personal, restricted or internal information, do not process it; ask the user to remove it from the workspace.
9. If the project scope changes to include restricted data, stop and obtain an approved data-handling and access-control design before processing it.

## 3. Small, approved checkpoints

For every task:

1. Read `AGENTS.md` and the relevant detailed anchor documents.
2. Check `STATUS.md` for the current milestone and known issues.
3. Explain the proposed approach and files to change before substantial edits.
4. Implement only the requested checkpoint. Do not silently continue into later milestones.
5. Add/update tests and run them.
6. Report actual commands and results. Never claim a test passed unless it was run successfully.
7. Show failures and limitations honestly.
8. Wait for human review before moving to the next checkpoint.
9. If architecture must change, stop and propose the change with reasons and impact.

## 4. Source integrity and provenance

1. Never modify or overwrite original PDFs in `documents/`.
2. Store derived outputs separately.
3. Preserve page boundaries and source identity throughout extraction, cleaning, chunking, retrieval and citations.
4. Every chunk must trace to a real document and page range.
5. Never fabricate page numbers, document names, section titles or citations.
6. Do not summarise away source details during ingestion.
7. Preserve numbers, dates, clauses, tables, exceptions and qualifiers.
8. Flag poor or incomplete extraction rather than silently accepting it.

## 5. Ingestion and database safety

1. Ingestion must be repeatable and idempotent.
2. Use SHA-256 and processing configuration/version to detect changes.
3. Skip unchanged, successfully processed content.
4. Resume failed page extraction without repeating successful pages.
5. When content changes, replace affected indexed content safely and transactionally.
6. Never automatically delete database content just because a file is temporarily absent.
7. Use Alembic migrations for schema changes; no undocumented manual schema edits.
8. Use parameterised SQL or safe ORM operations.
9. Keep credentials in environment variables, never source code.
10. Never expose PostgreSQL directly to the browser.

## 6. OCR and AI provider rules

1. Provider modules must be thin functions or small classes, not elaborate abstraction hierarchies.
2. Application code must not call Gemini SDK methods throughout the codebase; use provider functions such as `extract_page`, `embed_documents`, `embed_query` and `generate_answer`.
3. Keep provider/model names, API keys and dimensions configurable.
4. Verify current model names, quotas, supported dimensions and API parameters before implementation.
5. OCR must be page-level, resumable and faithful transcription, not summarisation.
6. Use deterministic settings such as temperature 0 where supported by the selected model/API.
7. Mark unreadable text as `[illegible]`; never guess.
8. Validate structured model output before storing it.
9. Classification is optional and must not block ingestion.
10. Do not silently change embedding model or dimensions. Re-embedding and evaluation are required.

## 7. RAG correctness

1. Institutional claims must be grounded in retrieved evidence.
2. Do not fill policy gaps with general model knowledge or guesses.
3. Citations must be resolved from actual retrieved records by backend code.
4. Insufficient evidence must lead to abstention or clarification.
5. Conflicting documents must be surfaced, not silently reconciled.
6. Consider document versions/effective dates when available.
7. Similarity scores alone do not prove answer correctness.
8. Keep retrieval, generation and citation validation independently testable.
9. Log retrieval IDs, scores and source metadata during development without logging sensitive personal data.

## 8. Code structure and frontend/backend boundary

1. Keep modules focused and avoid monolithic files.
2. Use clear names, type hints where useful and meaningful error handling.
3. Keep API request/response schemas explicit.
4. Keep React and FastAPI separate; communicate through documented API contracts.
5. Never place provider API keys or database credentials in frontend code.
6. Keep configuration separate from business logic.
7. Add tests for important transformations and database behaviour.
8. Do not introduce an abstraction without a current use case or a clear portability benefit.
9. Update documentation when an approved decision changes.

## 9. Git and agent safety

1. Initialise Git before substantial implementation.
2. `.gitignore` must explicitly ignore `documents/`, `data/`, `.env`, virtual environments, caches, generated files and local database artefacts.
3. Review diffs before accepting agent-generated changes.
4. Commit after verified checkpoints.
5. Do not make broad destructive changes without approval.
6. Do not give coding agents unrestricted production credentials or permission to incur cloud costs.
7. Do not assume the agent's workspace rules automatically load; explicitly instruct it to read `AGENTS.md` at the start of a session/task.

## 10. Definition of done

A checkpoint is complete only when functionality exists, relevant tests were actually run, expected behaviour was demonstrated, errors/limitations were recorded, a human reviewed it, documentation was updated and a working Git checkpoint was created.

**The coding agent is an implementation assistant. The project owner remains responsible for architecture, review and acceptance.**
