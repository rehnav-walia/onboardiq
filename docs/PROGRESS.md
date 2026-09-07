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

**Status: Code-complete, paused before final sign-off.** Committed in
`ac21906`.

All extraction/verification logic, data entities, and the
`GET .../extraction` endpoint are implemented and covered by 70 backend
tests (all with the LLM call mocked — defensive JSON parsing, all three
extraction outcomes, idempotency, audit logging, 20+ US-14 match-tolerance
edge cases). Graceful degradation is verified live (not just in tests):
submitting an application and uploading a document with no
`ANTHROPIC_API_KEY` configured correctly degrades to `AI_UNAVAILABLE`,
routes to `PENDING_REVIEW`, and still returns a normal `201` — no error
surfaced to the applicant.

**Paused (not a blocker):** a real, non-mocked vision extraction call
against the actual Anthropic API has not been made yet — the user has a
payment issue on their Anthropic account that needs resolving first. Per
the user's direction, this is deferred until shortly before final
demo/submission, and Phase 3 has proceeded without waiting on it. A
synthetic test ID image is already prepared (deliberately includes a
middle name and a DD/MM/YYYY date, to exercise PARTIAL_MATCH and
date-normalization on a real call once it happens). Until then, every
application a reviewer sees carries the `AI_UNAVAILABLE` extraction state —
which is exactly the condition Phase 3's review screen was built and
tested against, so nothing downstream is blocked by this.

## Phase 3 — Reviewer queue & human decision (US-19, 22, 23, 24, 26, 27)

**Status: Complete.**

- **Reviewer queue** (`GET /api/reviewer/queue`, paginated): lists only
  `PENDING_REVIEW`/`INFO_REQUESTED` applications, tested against a 50+ row
  seeded dataset.
- **Side-by-side review screen**: submitted vs. extracted data, mismatches
  highlighted with both an icon and a text label (not colour alone),
  low-confidence fields marked, document previewed on the same page. When
  extraction is `AI_UNAVAILABLE` or `UNREADABLE` (the only state currently
  reachable, per Phase 2 above), the screen shows a clear banner and falls
  back to a manual-review layout instead of a comparison it can't make —
  this was exercised live, not just in tests.
- **Decisions**: Approve / Reject / Request More Information, with
  reasoning mandatory for the latter two, enforced both client- and
  server-side. A decision can't be submitted twice (gated on
  `Application.status == PENDING_REVIEW` server-side, not just a disabled
  button) — the Decision row, status transition, and audit entry commit
  as one atomic write.
- **No auto-approval (US-24), proven by an automated test**: a
  whole-codebase scan (`tests/test_no_auto_approval.py`) asserts
  `ApplicationStatus.APPROVED` appears in exactly one place outside its own
  enum definition — `crud.create_decision`, reachable only through an
  endpoint that requires a validated, non-blank `reviewer_id`. Documented
  as a stated design principle in the README.
- **Explainability (US-26)**: the frontend's `AIValue` component refuses to
  render an AI value at all if its justification is empty — enforced
  structurally, not by convention.
- **Append-only audit log (US-27)**: every status transition — submission,
  processing start, extraction outcome, verification, decision — writes an
  entry; a full-lifecycle test asserts the exact ordered trail. No
  update/delete endpoint exists.

100 backend tests pass (70 from Phases 1–2 + 30 new). Verified live in a
real browser against running dev servers: submitted two applications,
uploaded documents, confirmed both landed in the queue, opened the review
screen (AI_UNAVAILABLE banner + manual comparison layout, since no real
extraction has run yet — see Phase 2), confirmed Reject is blocked without
reasoning, completed a Reject with reasoning on one and an Approve on the
other, and confirmed both correctly disappeared from the queue afterward
with a complete audit trail and a "Decision recorded" panel replacing the
form. No horizontal scrolling at 640px, 1100px, or 1280px viewport widths.

Since no real extraction has run yet, the live walkthrough above only
exercised the AI_UNAVAILABLE fallback layout — not the actual side-by-side
comparison grid with real MATCH/PARTIAL_MATCH/MISMATCH data. To verify
that rendering honestly (rather than leaving it covered only by backend
tests), a synthetic SUCCESS extraction result was seeded directly into the
database via the app's own `crud` functions (bypassing the LLM entirely,
clearly a test seed rather than a real result) and viewed in the browser:
confirmed the MATCH row (green, ✓), a deliberately low-confidence field
(⚠ Low confidence (55%) badge, correctly computed against the configured
threshold), and a deliberate ID-number MISMATCH (red, ⚠, with the specific
"submitted X does not match document's Y" justification) all render
correctly and without colour being the only distinguishing signal.

## Not yet started
Risk scoring (F5 — also why the queue doesn't show a risk level yet: it
isn't computed until US-16), the RAG policy assistant (F10), audit log
export (US-28), and the applicant-facing resubmission loop after Request
More Information (US-25).
