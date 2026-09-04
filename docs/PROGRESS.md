# Build Progress

Tracks status against the PRD's build sequence (section 12). Updated as each
phase lands — see git history for full detail; this is a snapshot, not a
changelog.

## Phase 1 — Application intake & document upload (US-01, 02, 04, 05, 06)

**Status: Complete.** Committed in `8a8780e`.

Backend (FastAPI) and frontend (React) scaffold, `Application` and
`Document` data entities, multi-step form with inline validation, and KYC
document upload with content-sniffed type validation and inline preview.
32 backend tests pass; verified end-to-end in a real browser against a
running dev server (Node.js and Python properly installed, not a portable
workaround).

## Phase 2 — AI document extraction & cross-verification (US-09–US-14)

**Status: In progress, paused.** Code committed in `ac21906`; paused before
final sign-off pending a real LLM verification.

### What's done and verified
- Extraction pipeline (`backend/app/pipeline.py`), Anthropic vision client
  (`backend/app/llm/`), named prompt template
  (`backend/prompts/document_extraction.txt`), and cross-verification logic
  (`backend/app/verification.py`) are all implemented.
- New data entities: `ExtractionResult`, `VerificationResult`, and a
  minimal append-only `AuditLogEntry`.
- New endpoint: `GET /api/applications/{reference_id}/extraction`.
- **70/70 backend tests pass** (32 from phase 1 + 38 new), all with the LLM
  call mocked — covering defensive JSON parsing, all three extraction
  outcomes (SUCCESS / UNREADABLE / AI_UNAVAILABLE), idempotency, audit
  logging, and 20+ US-14 match-tolerance edge cases (exceeds the 10-case
  DoD minimum).
- **Graceful degradation verified live**, not just in tests: started the
  real backend, submitted an application, and uploaded a real JPEG via curl
  with no `ANTHROPIC_API_KEY` configured. Confirmed via the raw HTTP
  responses that the upload still returned a normal `201` (no error
  surfaced to the applicant), the application moved to `PENDING_REVIEW`,
  and `GET .../extraction` correctly reported `AI_UNAVAILABLE` with a
  plain-language justification.

### Current blocker
No real (non-mocked) vision extraction call has been made against the
actual Anthropic API yet — that requires a live `ANTHROPIC_API_KEY`, which
isn't available in this environment. **Paused, waiting on the user to add
`ANTHROPIC_API_KEY` to `backend/.env`** (gitignored, never committed) so a
real extraction can be run and the true AC/DoD status reported per story.

A synthetic test ID image has been prepared (deliberately includes a middle
name and a DD/MM/YYYY date, to exercise the PARTIAL_MATCH and
date-normalization logic on a real call, not just simple exact matches).

### Next steps once unblocked
1. Run one real extraction against the synthetic test image.
2. Confirm the response parses correctly and produces sensible
   confidence/justification values.
3. Report final per-story AC/DoD status for US-09–US-14.

## Not yet started
Risk scoring (F5), reviewer work queue and review UI (F6/F7 — also why
US-11's "visually marked" and US-26/US-27's UI-facing DoD items aren't
testable yet), audit log viewing/export (US-27/US-28), and the RAG policy
assistant (F10).
