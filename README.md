# OnboardIQ — AI-Powered Banking Onboarding

Version 1.0

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

**Beyond the PRD:** a minimal reviewer login (see "Reviewer login" below) —
not one of the 30 stories, added afterward as a small, contained,
additive feature.

## Design principles (non-negotiable — see CLAUDE.md)

- **No auto-approval.** `ApplicationStatus.APPROVED` can only ever be
  assigned from one place in the entire codebase: `crud.create_decision`,
  which is only reachable through `POST /api/applications/{id}/decision` —
  an endpoint that requires a logged-in reviewer session (see "Reviewer
  login" below). The AI pipeline (`app/pipeline.py`) never references
  `APPROVED` at all. This is enforced by an automated, whole-codebase test
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

### Prerequisites

- **Python 3.10+** (the codebase uses `X | None` type-union syntax
  throughout, which requires it). Tested on **3.12** specifically —
  `requirements.txt` pins `chroma-hnswlib==0.7.5` because newer releases
  ship no prebuilt wheel for Windows/`cp312` and fail to build without
  MSVC Build Tools, so 3.12 is the version this project is actually
  verified against.
- **Node.js 18+** (required by Vite 5).

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

`ANTHROPIC_API_KEY` in `.env` can be left **blank** — this is a supported,
intentional way to run the whole app. Document extraction and the RAG
assistant's answers both degrade gracefully to manual review /
"unavailable" rather than erroring out (see "Design principles" above).
If you want live AI extraction and RAG answers, get a key from
[console.anthropic.com](https://console.anthropic.com) and set it there.

Demo reviewer credentials are intentionally committed in plaintext
(`backend/reviewer_accounts.json`) for local evaluation only — this
pattern is not used for any real user data and would not be appropriate
for a production deployment. Log in at `/reviewer/login` with
`reviewer_1`, `reviewer_2`, or `reviewer_42`, password `changeme123` for
all three (see "Reviewer login" below for the full rationale) — the login
page itself no longer displays these, by design.

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

The very first time this ingestion runs (whether via startup or the CLI
above), Chroma downloads a small (~90MB) local embedding model to a
machine-wide cache (`~/.cache/chroma/`) — this needs internet access
once, but is not per-clone: every project on the machine that uses
Chroma's default embedding function shares it afterward. Because of this,
the **first** `uvicorn` startup takes a few seconds longer than
subsequent ones — that's expected, not a hang.

To populate the reviewer queue with one demo application (a mismatch flag
and a HIGH risk breakdown) instead of applying through the UI, run
`python backend/seed_demo.py --reset` (stop the backend first — it needs
the database file free). Add `--full` (`--reset --full`) to also seed four
more applications in varied states (approved, rejected, info-requested, an
overdue pending one) so the reviewer queue's summary stats bar has real
numbers to show; see `python backend/seed_demo.py --help` for details. The
extraction it shows is simulated, not a real Anthropic API call, since
`ANTHROPIC_API_KEY` is left blank by default for local dev.

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

Run the frontend's unit tests (plain modules like `validation.js` and
`jumpToApplication.js`, via Node's built-in test runner — this project has
no other frontend test framework):

```bash
cd frontend
npm test
```

## Reviewer login

Not part of the original 30-story PRD — added afterward as a small,
contained addition. Reviewer actions (the queue, and submitting a
decision) require logging in at `/reviewer/login`. Applicants never
authenticate at all; nothing about the applicant flow changed.

Three fixed demo accounts, defined in `backend/reviewer_accounts.json`:

| Username | Password |
|---|---|
| `reviewer_1` | `changeme123` |
| `reviewer_2` | `changeme123` |
| `reviewer_42` | `changeme123` |

This is deliberately **not** a production authentication system: plaintext
demo passwords in a committed config file, and sessions are an in-memory
token map that's cleared on every backend restart (see `backend/app/auth.py`
for the full rationale). A decision's `reviewer_id` is always the logged-in
username — there is no free-text reviewer ID field anywhere in the API or
UI, so a reviewer can no longer attribute a decision to anyone but
themselves.

## Configuration

All thresholds, timeouts, and paths are read from environment variables —
see `backend/.env.example` for the full list. Nothing is hardcoded in
application code (see CLAUDE.md conventions).

## Known limitations

- **Document extraction is simulated in the demo seed data.** With no
  `ANTHROPIC_API_KEY` configured (the default for local dev), the real
  pipeline degrades gracefully to `AI_UNAVAILABLE` rather than erroring
  out — so `backend/seed_demo.py` writes a synthetic but realistic
  extraction result directly, using the same real, deterministic risk
  function the live pipeline calls, rather than depending on a live API
  call. See "Running locally" above.
- **The intake form's inline email check is lighter than the server's.**
  The frontend's lightweight regex accepts a few malformed shapes
  (consecutive dots, a leading/trailing dot in the local part,
  hyphen-bounded domain labels, IP-literal domains, quoted local-parts)
  that the backend's Pydantic `EmailStr` validator rejects — see
  `docs/PROGRESS.md`'s "Inline field validation" entry for the full
  comparison. Such a value is only caught server-side, at final
  submission, not shown as an inline error while typing.
- **Rate limiting and reviewer sessions are in-memory and single-instance.**
  Both reset on every backend restart and aren't shared across worker
  processes or machines — appropriate for a single-instance demo/local
  app (CLAUDE.md's non-goals explicitly exclude production-grade
  security), not a multi-instance production deployment. Sessions are a
  module-level token map in `backend/app/auth.py`; the limiters are
  module-level instances in `backend/app/rate_limit.py`. v1.1 would keep
  this design for a single-container demo, run exactly one worker, and
  clear both on every scheduled reset.
- **Reference IDs are sequential, and some application reads need no
  login.** IDs follow `ONB-<year>-<row id>` (`_generate_reference_id` in
  `backend/app/crud.py`), so they can be guessed. The application record
  and its current decision (`backend/app/routers/applications.py`) and the
  document list and file download (`backend/app/routers/documents.py`)
  are open by design, because applicants never log in and their status
  view uses them; reviewer-only reads (extraction, risk, audit log and
  export, decision history) do require a login. Drafts can likewise be
  edited, and documents uploaded, by anyone holding a reference ID. This
  is fine for local use with sample data. It is not safe for a public
  instance where strangers could enter real data; v1.1's demo plan
  disables applicant submission and upload in demo mode instead (see
  `docs/DEPLOYMENT_PLAN.md`).
- **Rate limits key on the client IP as the server sees it.**
  `client_ip` in `backend/app/rate_limit.py` uses the socket's peer
  address. Locally that is the real client. Behind a hosting proxy it
  would be the proxy's address, so every visitor would share one login
  and one submission budget. v1.1 would start uvicorn with proxy headers
  trusted only from the host's own proxy.
- **Free-text fields have no length cap, and the CSV export does not
  neutralise formulas.** `DecisionCreate.reasoning` in
  `backend/app/schemas.py` has no maximum length (nor do the applicant
  text fields or the policy assistant question). The audit export in
  `backend/app/routers/applications.py` writes cells with Python's
  `csv.writer`, which handles commas, quotes and newlines but leaves a
  cell beginning with `=`, `+`, `-` or `@` as-is, so a spreadsheet may
  treat it as a formula. Acceptable when the only people typing are you
  and your own reviewers; v1.1 would cap reasoning length and prefix such
  cells with `'` on export.
- **Demo reviewer credentials are committed on purpose.**
  `backend/reviewer_accounts.json` holds three demo accounts with a
  shared plaintext password. The login page
  (`frontend/src/pages/ReviewerLoginPage.jsx`) does not display them; they
  are listed in this README instead, so anyone cloning the repo can try
  the reviewer flow immediately (see "Running locally" and "Reviewer
  login" above). v1.1's public demo would read its reviewer accounts from
  environment variables on the host instead.

## Future enhancements

- Dark/light theme toggle.
- Public deployment.
- Shared storage for rate limits and reviewer sessions, so both survive a
  restart and work correctly across multiple instances.
