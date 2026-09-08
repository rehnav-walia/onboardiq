# OnboardIQ — AI-Powered Banking Onboarding

Portfolio project demonstrating "domain + AI infusion" in banking onboarding.
See [docs/PRD.md](docs/PRD.md) for the full product requirements and
[CLAUDE.md](CLAUDE.md) for the non-negotiable design principles this project
is built against.

## Status: all 6 phases of the PRD build sequence complete

See [docs/PROGRESS.md](docs/PROGRESS.md) for the up-to-date, per-phase status.
Implemented: application intake, document upload, and save-and-resume
drafts (Phases 1 & 6's US-03); AI document extraction and
cross-verification (Phase 2 — code-complete, verified against mocked LLM
responses; a real API key is not yet available, see PROGRESS.md); the
reviewer queue, side-by-side review screen, and approve/reject/request-info
decision flow, including the full resubmission loop after Request More
Information (Phase 3 + Phase 6's US-25); composite risk scoring
(including a declared-vs-detected document type check), rule-based checks,
risk breakdown, and queue sort/filter/ageing (Phase 4 + Phase 6's
US-08/US-15); a RAG policy assistant answering onboarding questions from
ingested policy documents, with citations (Phase 5 — retrieval is real and
local, no API key needed; only the final answer-synthesis call needs one,
see PROGRESS.md); document replacement with version retention for audit
(Phase 6's US-07); and CSV/JSON audit trail export (Phase 6's US-28). All
30 user stories in `docs/PRD.md` are implemented.

## Design principles (non-negotiable — see CLAUDE.md)

- **No auto-approval.** `ApplicationStatus.APPROVED` can only ever be
  assigned from one place in the entire codebase: `crud.create_decision`,
  which is only reachable through `POST /api/applications/{id}/decision` —
  an endpoint that requires a validated, non-blank `reviewer_id`. The AI
  pipeline (`app/pipeline.py`) never references `APPROVED` at all. This is
  enforced by an automated, whole-codebase test
  (`backend/tests/test_no_auto_approval.py`), not just a code review
  convention — it scans every source file and fails if the string
  `ApplicationStatus.APPROVED` ever appears anywhere outside that one
  function.
- **No unexplained AI output.** Every extracted field and every
  submitted-vs-extracted comparison carries a plain-language justification
  before it can render. The frontend's `AIValue` component enforces this
  structurally: it refuses to display a value at all if no justification is
  present, rather than relying on every call site remembering to check.
- **Append-only audit log.** `AuditLogEntry` rows are only ever inserted,
  never updated or deleted — there is no such function in `crud.py` and no
  such route in the API.
- **Graceful degradation.** If the LLM is unavailable or its response can't
  be parsed, the application is routed to manual review with a plain
  explanation — it never returns an error to the applicant.

## Project layout

```
backend/    FastAPI application (Python)
frontend/   React application (Vite)
docs/       PRD and other product documentation
```

## Running locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The API is served at `http://localhost:8000`. SQLite data lives in
`backend/data/`, uploaded files in `backend/storage/`, and the local RAG
vector store in `backend/data/chroma/` — all git-ignored and created
automatically on first run. The sample policy documents in
`backend/policy_documents/` are ingested automatically on startup if the
vector store is empty; if you edit them, re-ingest explicitly:

```bash
cd backend
python -m app.rag.ingest_cli
```

Run the backend test suite:

```bash
cd backend
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies `/api` requests
to the backend on port 8000 (see `frontend/vite.config.js`).

## Configuration

All thresholds, timeouts, and paths are read from environment variables —
see `backend/.env.example` for the full list. Nothing is hardcoded in
application code (see CLAUDE.md conventions).
