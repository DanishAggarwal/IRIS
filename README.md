# IRIS — Institutional RAG Assistant

**IRIS (Information Retrieval and Intelligence System)** is a local-first, institutional-document question-answering assistant designed for Punjab Engineering College (PEC). It empowers students and faculty to ask natural language questions about academic curricula, course handouts, academic regulations, and institutional policies, receiving answers strictly grounded in official institutional documents with verified page-level citations.

---

## Architecture Overview

- **Backend**: Python 3.14 + FastAPI
- **Database**: PostgreSQL 16 + `pgvector` (Docker container on port `5433`)
- **ORM & Migrations**: SQLAlchemy 2.0 + Alembic
- **Embeddings & LLM**: Google Gemini (`gemini-embedding-001` with 768 dimensions, `gemini-3.5-flash-lite` for OCR and generation)
- **Frontend**: React 19 + TypeScript + Vite + Lucide Icons + Tailwind CSS
- **Authentication**: Official Google Identity Services OAuth 2.0 with backend token verification, institutional domain enforcement (`@pec.edu.in`), administrator allowlist, and server-side HttpOnly session cookies
- **Storage**: Multi-tenant database design isolating conversations and messages per authenticated user

---

## Prerequisites

1. **Docker & Docker Compose** (for PostgreSQL + pgvector)
2. **Python 3.11+** (virtual environment recommended)
3. **Node.js 18+** and **npm**
4. **Google Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/))
5. **Google Cloud Console OAuth 2.0 Client ID** (for Google Sign-In)

---

## Setup & Configuration

### 1. Database (Docker Compose)

Start the local PostgreSQL container with the `vector` extension:
```bash
docker compose up -d
```
Verify the container is running on port `5433`:
```bash
docker ps
```

### 2. Backend Environment Setup

Create and activate a virtual environment, then install dependencies:
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Key environment variables in `.env`:
```ini
# PostgreSQL
DATABASE_URL=postgresql+psycopg://iris:iris_password@localhost:5433/iris_db

# Gemini API
GEMINI_API_KEY=your-gemini-api-key

# Google OAuth & Authentication
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
ALLOWED_EMAIL_DOMAINS=pec.edu.in
ADMIN_EMAILS=your-personal-email@gmail.com
APP_ENV=development
```

### 3. Google OAuth 2.0 Client ID Configuration

To enable real Google Sign-In with institutional `@pec.edu.in` accounts and personal administrator accounts:

1. **Google Cloud Console Project**:
   - Open the [Google Cloud Console Credentials Page](https://console.cloud.google.com/apis/credentials).
   - Create a project (e.g. `IRIS-PEC`) or select an existing one.

2. **Configure OAuth Consent Screen**:
   - Go to **APIs & Services** -> **OAuth consent screen**.
   - Select **User Type**: **External** (or **Internal** if using a PEC Google Workspace tenant).
   - App name: `IRIS Institutional Assistant`.
   - User support email: your email.
   - Scopes: `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`.
   - **Test Users** (critical while publishing status is "Testing"):
     - Add your personal Google email (e.g. `your.personal.email@gmail.com`).
     - Add any PEC student/faculty test accounts (`@pec.edu.in`).

3. **Create OAuth 2.0 Web Client ID**:
   - Go to **Credentials** -> **Create Credentials** -> **OAuth Client ID**.
   - Application type: **Web application**.
   - Name: `IRIS Web Local`.
   - **Authorized JavaScript origins**:
     - `http://localhost:5173`
     - `http://localhost:8000`
   - **Authorized redirect URIs**:
     - `http://localhost:5173`
     - `http://localhost:8000`
   - Click **Create**. Copy the generated **Client ID** (e.g. `1234567890-abcdefg...apps.googleusercontent.com`).
   - *(Note: Client Secret is not needed for this client-side Google Identity Services flow).*

4. **Apply Client ID to Environment Files**:
   - In root `.env`:
     ```ini
     GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
     ALLOWED_EMAIL_DOMAINS=pec.edu.in
     ADMIN_EMAILS=your.personal.email@gmail.com
     APP_ENV=development
     ```
   - In frontend `frontend/.env` (create by copying `frontend/.env.example`):
     ```ini
     VITE_API_BASE_URL=http://localhost:8000
     VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
     ```
   - Restart both backend and frontend servers after creating or editing `.env` files.

> **Local Development Fallback**: When `VITE_GOOGLE_CLIENT_ID` is unset and `APP_ENV=development`, IRIS automatically renders local mock login buttons (`dev_mock_pec_student`, `dev_mock_admin`). As soon as `VITE_GOOGLE_CLIENT_ID` is populated, mock login buttons are replaced with the official Google Sign-In button.

### 4. Database Migrations

Apply all Alembic migrations (including `0005_add_auth_and_conversations`):
```bash
alembic upgrade head
```

### 5. Frontend Setup

In a separate terminal, navigate to `frontend/`:
```bash
cd frontend
cp .env.example .env
npm install
```

---

## Running the Application

### Start the FastAPI Backend
From the root workspace (with `.venv` activated):
```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```
The backend API documentation is available at `http://127.0.0.1:8000/docs`.

### Start the React Frontend
From the `frontend/` directory:
```bash
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Features & User Experience

- **Institutional Authentication**:
  - Restricts access to students and staff with `@pec.edu.in` accounts.
  - Allows designated administrators with personal Google accounts (e.g. `@gmail.com`) via `ADMIN_EMAILS`.
  - Secure session management via cryptographic 32-byte tokens stored in HttpOnly cookies with SHA-256 database hashing.
- **Persistent Conversation History**:
  - Sidebar displaying past conversation threads.
  - Seamless "New Chat" creation.
  - In-place conversation renaming and thread deletion with modal confirmation.
  - Strict user ownership isolation (users can only access their own conversations).
- **Grounded Institutional RAG**:
  - Semantic similarity search using `pgvector` and Gemini embeddings over official syllabus and course handouts.
  - Zero hallucination policy: responses classify into `answered`, `clarification_needed`, or `handoff_recommended`.
  - Verifiable citations with document filename, exact page range, and section titles.
- **System Health Monitoring**:
  - Real-time connection badge verifying backend liveness and database readiness.

---

## Testing

### Backend Test Suite
Run the 128 pytest tests covering database, extraction, cleaning, chunking, embeddings, retrieval, RAG generator, API endpoints, and authentication:
```bash
pytest -v
```

### Frontend Test Suite
Run the 44 Vitest tests covering API integration, UI components, authentication hooks, conversation sidebar, and end-to-end user flows:
```bash
cd frontend
npm test
```

### Production Frontend Build
Verify TypeScript compilation and bundling:
```bash
cd frontend
npm run build
```
