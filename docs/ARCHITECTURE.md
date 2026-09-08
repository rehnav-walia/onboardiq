# Architecture

High-level shape of the system. See [PRD.md](PRD.md) for product
requirements and [../CLAUDE.md](../CLAUDE.md) for the non-negotiable
design principles this architecture exists to serve.

## Components

- **React frontend** — a single app serving two audiences: the applicant
  UI (multi-step form, save/resume, document upload, status view) and the
  reviewer UI (login, queue, side-by-side review screen, decisions, audit
  export). No server-side rendering; talks to the backend entirely over
  `/api/*`.
- **FastAPI backend** — the only thing any client talks to. Owns all
  business logic: intake validation, orchestrating AI extraction and
  cross-verification, risk scoring, the reviewer decision flow, the
  append-only audit log, and reviewer authentication.
- **SQLite** — system of record for applications, documents, extraction
  and verification results, risk assessments, decisions, and the audit
  log itself. Accessed only through the backend.
- **Chroma** — a local vector store holding embeddings of the bank's
  policy/FAQ documents, used only by the RAG policy assistant. Ingestion
  and retrieval need no external API — embeddings are computed locally.
- **Anthropic API** — used for two things only: vision-based extraction of
  identity fields from an uploaded document, and composing the RAG
  assistant's final answer from retrieved policy chunks. Every other
  decision in the system (risk scoring, match logic, no-auto-approval) is
  deterministic code, not a model call.

## Data flow

```
                         ┌─────────────────────┐
                         │   React Frontend     │
                         │  (Applicant +        │
                         │   Reviewer UI)        │
                         └──────────┬───────────┘
                                    │  HTTPS / JSON (/api/*)
                                    ▼
                         ┌─────────────────────┐
                         │   FastAPI Backend    │
                         │  (validation, risk    │
                         │   scoring, decisions, │
                         │   reviewer auth)      │
                         └──────────┬───────────┘
                     ┌──────────────┼──────────────────┐
                     ▼              ▼                  ▼
            ┌────────────────┐ ┌──────────┐   ┌──────────────────┐
            │     SQLite      │ │  Chroma  │   │   Anthropic API   │
            │ applications,   │ │ (policy  │   │ (vision extraction│
            │ documents,      │ │document  │   │  + RAG answers)   │
            │ decisions,      │ │embeddings)│   └─────────┬────────┘
            │ audit log       │ └────┬─────┘             │
            └────────┬────────┘      │                   │
                     ▲                │                   │
                     │                ▼                   │
                     │        retrieved policy             │
                     │        chunks flow back              │
                     │        into the backend               │
                     │        for answer synthesis            │
                     │                                         │
                     └─────────── every step writes ───────────┘
                                  an audit log entry
                                  (append-only — SQLite)
```

Two request paths exercise this differently:

- **Applicant onboarding**: Frontend → Backend → (Anthropic API for
  extraction) → Backend compares extracted vs. submitted data → risk
  scored → SQLite. If the Anthropic API call fails or times out, the
  backend does **not** error out to the applicant — it routes the
  application to manual review with a plain-language flag
  (`AI_UNAVAILABLE`) and continues. See "Graceful degradation" below.
- **Policy assistant question**: Frontend → Backend → Chroma (retrieve
  top-k relevant chunks, no API key needed) → Backend → Anthropic API
  (compose an answer from only those chunks) → Frontend. If no relevant
  chunks are found, the backend never calls the Anthropic API at all and
  returns "not found" directly.

## Append-only audit log

Every step above — application submission, extraction outcome,
verification result, risk assessment, a reviewer's decision — writes one
row to an `AuditLogEntry` table in SQLite. There is no update or delete
path for this table anywhere in the codebase; entries can only ever be
appended. A full application lifecycle produces a complete, chronologically
ordered trail, viewable per application and exportable as CSV/JSON.

## Graceful degradation

If the Anthropic API is unavailable — no API key configured, a network
failure, a timeout, or a response that doesn't parse into the expected
shape — the backend never returns an error to the applicant. The affected
step is marked `AI_UNAVAILABLE`, the reason is written to the audit log,
and the application is routed to a human reviewer for manual handling
instead. The applicant's request still completes normally (e.g. a
document upload still returns `201 Created`); only the review screen sees
that AI assistance wasn't available for that step.
