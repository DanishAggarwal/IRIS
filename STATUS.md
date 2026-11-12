# IRIS — Current Status

**Current stage:** Milestone 0 Complete — Ready for Milestone 0.5 / 1  
**Current focus:** Inspect the manually selected sample PDFs in `documents/` and set up document discovery and page inspection.

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

## Current milestone
**M0.5 / M1 — Sample PDF Inspection and Discovery**

## Sample Corpus in `documents/` (Public Allowlist)
1. `Course Handout of CSE 25261 Semester 04082025 Ver 1_0.pdf`
2. `Course Handout of CSE 25261 Semester 04082025 Ver 2_0.pdf`
3. `CSE_syllabus_24.pdf`

## Next checkpoints
1. Run PDF inspection / discovery script to compute SHA-256 hashes, page counts, and basic metadata.
2. Evaluate extractable digital text vs scanned/image-based pages.
3. Formulate retrieval evaluation criteria once sample corpus structure is characterized.

## Test Results from M0
- Command: `.venv\Scripts\pytest.exe -v tests/test_database.py`
  - `test_database_connection` PASSED
  - `test_vector_extension_active` PASSED
  - `test_vector_insert_and_l2_distance_search` PASSED
  - `test_vector_cosine_distance_search` PASSED
  - Result: 4 passed in 0.98s.

## Pending decisions / verification
- [ ] Verify current Gemini OCR/document-processing model/API and quotas.
- [ ] Verify current Gemini embedding model name, supported dimensions and task types.
- [ ] Compare 768 and 1536 embedding dimensions on the evaluation set before finalising.
- [ ] Evaluation question benchmark deferred by user instruction until corpus inspection.

## Known constraints
- Port `5433` is used on localhost for the Docker `pgvector` container to prevent conflicts with local host PostgreSQL 18.
- No authentication or persistent conversation history in the prototype.
- No multi-agent architecture.
- No cloud database or deployment yet.
- Only process public files inside `documents/`; never send personal, restricted or internal material to external APIs.
