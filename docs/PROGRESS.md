# Build Progress

Tracks status against the PRD's build sequence (section 12). Updated as each
phase lands — see git history for full detail; this is a snapshot, not a
changelog. See [ARCHITECTURE.md](ARCHITECTURE.md) for the system's
component diagram and data flow.

## At a glance

**Status: feature-complete.** All 6 phases of the PRD build sequence are
complete and committed — **all 30 user stories in `docs/PRD.md` are
implemented** — plus one addition beyond the original scope: a minimal
reviewer login, also complete and verified. 231 backend tests pass (fresh
run, no cache); every phase and the reviewer-login addition have been
verified end-to-end in a real browser, not just by automated tests — see
each section below for exactly what was checked live vs. covered by
tests.

**Addition beyond the 30 stories — reviewer login: complete.** Not in the
original PRD — requested and added afterward as a small, contained,
additive feature (see "Addition: reviewer login" below for the full
writeup). It does not change any of the 30 stories' own behavior — only
*how* a reviewer's identity gets attached to a decision. The queue,
decision submission, and every reviewer-only read on an application
(extraction, risk, audit log and its export, decision history) all
require that same login. One exception remains, deliberately: the
document file endpoint is shared with the applicant's own (login-free, by
design) document preview and can't be gated the same way without breaking
that existing, tested behavior — see that section for the full reasoning.

**Two things are still genuinely pending — both external to the code, not
implementation gaps:**

1. **Real `ANTHROPIC_API_KEY` verification for Phase 2 and Phase 5** —
   blocked on a payment issue on the Anthropic account, not on this
   codebase. A real (non-mocked) call to the Anthropic API has not been
   made yet, for either **Phase 2** (vision-based document extraction) or
   **Phase 5** (the RAG assistant's final answer-synthesis step).
   Everything else in both phases is genuinely live-verified, not mocked:
   - Phase 2: defensive JSON parsing, idempotency, and graceful
     degradation to `AI_UNAVAILABLE` are all confirmed live against a
     running server.
   - Phase 5: ingestion, chunking, local embedding, and real semantic
     retrieval need no API key at all and are fully live-verified; only
     the final "compose a natural-language answer" step degrades
     gracefully pending the key.

   Once a key is available: run one real document extraction and one real
   chat question through the existing (already-built, already-tested)
   code paths to close this out. No implementation work is expected to
   change — this is a verification step, not a feature gap. Phase 6's own
   declared-vs-detected document type check (US-15) was live-verified with
   a synthetic extraction result for the same reason — see Phase 6 below.
2. **Demo video/GIF recording** — still to be done, on the user's end. A
   full step-by-step walkthrough script was prepared (submit → AI flags a
   mismatch → reviewer sees the explanation → approves, condensed to a
   suggested 4–5 screen, 60–90s cut) and one demo application was seeded
   for the "mismatch" scene, using the same seed-and-clean-up approach as
   every other live verification in this document. The seed script and
   seeded dev database were removed after the walkthrough was prepared —
   nothing from that session is left in the repo or the local database.

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

## Phase 4 — Risk scoring, rule checks & queue sort/filter/ageing (US-16, 17, 18, 20, 21)

**Status: Complete.**

- **Composite risk scoring (US-16)** (`app/risk.py`): a documented, additive
  point system over mismatch severity (MISMATCH weighted higher than
  PARTIAL_MATCH), document readability (UNREADABLE/AI_UNAVAILABLE), extracted
  field confidence, declared-vs-detected type mismatch, and the rule flags
  below — bucketed into LOW/MEDIUM/HIGH by two documented thresholds. Pure
  and deterministic: no clock, no LLM call, same inputs always produce the
  same output (asserted directly by a test). Advisory only, everywhere —
  nothing reads `risk_level` to gate a status change; the codebase-scan test
  from Phase 3 continues to prove `APPROVED` is only ever set from the
  decision flow, risk included.
  - At the time this phase shipped, declared-vs-detected type mismatch
    always contributed nothing, because there was no UI yet to capture a
    *declared* type — the parameter existed in the scoring function's
    signature, ready to wire in, but wasn't faked with a placeholder value.
    Phase 6 (US-08/US-15) is what actually populates it — see below.
- **Rule-based checks (US-17)** (`app/rules.py`): minimum age (configurable
  via `MINIMUM_APPLICANT_AGE`), future-dated DOB, and document expiry — all
  pure functions over already-known data, so they run and produce real
  signal even when AI extraction is `AI_UNAVAILABLE`. Document expiry
  required extending the LLM extraction schema/prompt with a 5th field
  (`expiry_date`, nullable — many ID documents don't show one at all).
- **Risk breakdown in the reviewer UI (US-18)**: a dedicated "Risk
  assessment" section shows the level plus every contributing factor in
  plain language — the API response for `GET .../risk` doesn't even include
  a numeric point value, so there's no way for the frontend to accidentally
  show a bare score. Verified live: a deliberately-engineered HIGH risk
  application (under-minimum-age applicant + AI_UNAVAILABLE) was approved
  through the actual UI, and the risk badge stayed visible on the approved
  application afterward rather than being hidden or reset.
- **Queue sort & filter (US-20)**: `GET /api/reviewer/queue` now accepts
  `status`, `risk_level`, `sort_by` (submission time or risk level — risk
  severity ordering needed a SQL `CASE` expression, since the stored text
  values don't sort alphabetically in severity order), `sort_dir`, all
  server-side. Filter/sort/page state lives in the URL (`useSearchParams`),
  which is what actually makes it survive navigating to a review screen and
  back — including a real browser back-button press, and the in-app "Back to
  queue" link, which was originally a plain route link and silently dropped
  filters until caught during the live walkthrough and switched to
  `navigate(-1)`.
- **Ageing/overdue visibility (US-21)**: `Application.pending_review_since`
  is set once, the first time an application reaches `PENDING_REVIEW` (not
  reset by a later retry), and elapsed time is computed fresh on every
  queue request rather than stored. Timezone handling was verified
  concretely, not just assumed: seeded a row with a known aware-UTC
  timestamp 30 hours in the past and confirmed the computed elapsed hours
  matched, live in the browser, with the row correctly highlighted and
  filterable via "Overdue only."

148 backend tests pass (100 from Phases 1–3 + 48 new). Verified live: two
applications (one adult, one deliberately under the minimum age) produced
MEDIUM and HIGH risk respectively purely from real pipeline runs (not
seeded), both visible with correct badges and factor lists in the queue and
detail screen; sort-by-risk-level, status/risk filters, and the overdue
filter were all exercised interactively in the browser, not just asserted
in tests.

## Phase 5 — RAG policy assistant (US-29, US-30)

**Status: Complete**, with the same kind of honest split as Phase 2 between
what's genuinely live-verified and what's mocked pending an API key — see
below.

- **Ingestion & retrieval (US-29)** (`app/rag/`): three sample policy/FAQ
  markdown documents (`backend/policy_documents/`, committed to the repo)
  are chunked section-aware (markdown headings, with a sliding-window
  fallback for long sections — chunk size/overlap configurable via
  `RAG_CHUNK_SIZE`/`RAG_CHUNK_OVERLAP`), embedded, and stored in a local
  Chroma collection (`CHROMA_PERSIST_DIR`) — no external service, per
  CLAUDE.md's tech stack. Idempotent by construction: re-ingesting a
  document deletes its existing chunks first, so re-running never
  duplicates and correctly handles a document that has changed size.
  Ingestion reports a per-file chunk count, both from the CLI
  (`python -m app.rag.ingest_cli`) and via `ingest_directory()`'s return
  value.
  - **This entire half needs no Anthropic API key at all** — Chroma's
    default embedding function runs a small ONNX model locally. That
    means ingestion and retrieval are **fully, genuinely live-verified**,
    not mocked: real chunking, real local embeddings, real semantic
    search, all confirmed working end to end via curl, the ingestion CLI,
    and the browser.
  - One environment note worth recording: `chromadb`'s dependency
    `chroma-hnswlib` has no prebuilt wheel for the newest release on
    Windows/Python 3.12, and building it from source needs MSVC Build
    Tools (not installed here). Pinned to `chroma-hnswlib==0.7.5`, which
    does ship a prebuilt wheel — works cleanly, documented in
    `requirements.txt`.
- **Grounded chat assistant (US-30)** (`app/rag/assistant.py`, `POST
  /api/policy-assistant/ask`, and a `PolicyAssistantChat` widget present
  throughout the applicant flow): retrieves real chunks, then asks Claude
  to compose an answer using only a numbered list of those chunks. The
  model never gets to invent which sources exist — it picks from the
  numbered list we gave it, and we translate its choices back into real
  citation metadata ourselves; an out-of-range or fabricated index is
  silently dropped, never trusted. This makes "every citation maps to a
  real, retrievable source chunk" a structural guarantee, verified
  directly by a test that looks each citation back up in the full stored
  set (not just the query that produced it).
  - **This step does need the Anthropic API**, which isn't available yet
    (same payment issue as Phase 2). Verified live: asking real questions
    through curl and through the actual chat widget in the browser
    correctly performs real retrieval (`retrieved_chunk_count` > 0,
    semantically correct — e.g. an account-types question ranked all
    three `account_types_faq.md` sections top-3) and then gracefully
    degrades to a plain "unable to answer right now" message — no crash,
    no error surfaced. The full "answered with citations" and "declines an
    out-of-scope question" paths are verified with the LLM call mocked
    (`app.rag.assistant.run_text_completion`), the same pattern as Phase 2's
    extraction tests.
  - "Does not comment on the applicant's own application" is enforced two
    ways: a prompt-level instruction (can't be verified without a real
    call), and — more importantly — structurally: the assistant endpoint
    and every module under `app/rag/` are proven by an automated test to
    contain no reference to `Application`, any reference id, or any lookup
    function for one. There is no code path for application data to reach
    this feature at all, regardless of how well the model follows
    instructions.
  - Retrieved context is genuinely logged for debugging — caught and fixed
    a real gap during verification: the app never configured a log level,
    so the `logger.info(...)` call was silently dropped by Python's
    default WARNING threshold. Added `logging.basicConfig(level=logging.INFO)`
    and confirmed the retrieval log now actually appears.

180 backend tests pass (148 from Phases 1–4 + 32 new). Verified live: the
ingestion CLI run twice showed identical chunk counts (12 chunks, 3
documents) with no growth; curl and the browser chat widget both showed
real, semantically-correct retrieval before gracefully degrading on
answer synthesis.

## Phase 6 — Completeness: drafts, resubmission loop, export (US-03, 07, 08, 15, 25, 28)

**Status: Complete.** This is the final phase — all 30 PRD user stories are
now implemented.

- **Save and resume (US-03)**: `Application`'s applicant fields
  (`full_name`, `date_of_birth`, etc.) are now nullable, and a new
  `created_at` column (separate from `submitted_at`, which stays null until
  actual submission) is what reference-ID generation keys off for a draft.
  `POST /api/applications/draft` creates a `DRAFT` row and returns a
  reference ID immediately, however incomplete; `PATCH
  /api/applications/draft/{id}` saves further progress (only the fields
  actually sent are changed, so saving step 2 alone can't null out step
  1's already-saved values); `POST /api/applications/draft/{id}/submit`
  re-validates the now-complete field set with the *exact same* rules a
  direct submission goes through (`ApplicationCreate`) before transitioning
  to `SUBMITTED` — a draft can look incomplete or invalid at every
  intermediate save, but never becomes a real application without passing
  full validation. The original one-shot `POST /api/applications` path is
  completely unchanged and still the default for an applicant who doesn't
  need to save partway through. Draft applications are excluded from the
  reviewer queue by construction (queue queries only ever look at
  `PENDING_REVIEW`/`INFO_REQUESTED`, which a `DRAFT` can never be).
  - One correctness detail worth recording: since a draft can have a
    document attached before the application's own fields are known,
    extraction is deliberately deferred until the moment of actual
    submission (`submit_draft` triggers the pipeline itself if a document
    already exists) rather than running at upload time while still `DRAFT`
    — otherwise cross-verification would have nothing valid to compare
    against yet.
- **Replace an uploaded document (US-07)**: `Document` gained `version`
  (1-based), `superseded` (bool), `declared_type`, `detected_type`, and
  `type_mismatch` columns. Uploading a new document for an application that
  already has one marks every prior document `superseded=True` and never
  deletes it — the file, its `ExtractionResult` rows, and an explicit
  `DOCUMENT_REPLACED` audit entry all remain queryable, satisfying the DoD's
  "version retention verified in the data model" directly rather than by
  inference. A new upload/replace is only accepted while status is `DRAFT`,
  `SUBMITTED` (the ordinary first upload), or `INFO_REQUESTED` (a
  resubmission) — anything else (`PROCESSING`, `PENDING_REVIEW`, a final
  decision) is rejected with `409`, live-verified against a
  freshly-approved application.
  - Fixing this properly surfaced a real, pre-existing correctness gap:
    `VerificationResult` had no link to the document that produced it, so a
    resubmission's fresh comparison results would have silently piled up
    alongside an earlier round's in the same list. Added a `document_id`
    column and scoped both risk scoring and the `/extraction` API response
    to the *current* document only — verified by a test that resubmits and
    asserts exactly one row per comparable field, not one per round.
- **Declared document type + mismatch check (US-08/US-15)**: a new
  `DocumentType` enum (`PASSPORT`/`NATIONAL_ID`/`DRIVING_LICENCE`) is
  submitted alongside the file upload (multipart form field) and passed
  straight into the extraction prompt as context — that plumbing already
  existed from Phase 2 (`run_extraction`'s `declared_document_type`
  parameter), it just had no caller supplying a real value until now. Once
  extraction reports a detected type, `app.verification.compare_document_type`
  compares them (case/whitespace-insensitive, same normalization as every
  other text comparison in that module) and stores the result as
  `Document.type_mismatch` — `None` when there's nothing yet to compare,
  `True`/`False` once there is. This feeds directly into Phase 4's already
  present (but previously always-`None`) `declared_type_mismatch` parameter
  in `app/risk.py`, and renders as its own distinct banner next to the
  document preview — deliberately separate from the field-level
  MATCH/PARTIAL_MATCH/MISMATCH grid, per the DoD's "rendered distinctly."
  A mismatch never blocks a decision — verified live (see below).
- **Resubmission loop (US-25)**: no new state-machine code was needed
  beyond US-07's upload gating — `INFO_REQUESTED` already accepts a new
  document, and `pipeline.process_document` already re-processes whatever
  document it's given, so uploading a replacement naturally re-triggers
  extraction/verification and returns to `PENDING_REVIEW`. What *did* need
  fixing: `crud.get_decision` returned the *first* decision ever recorded
  for an application, which after a `REQUEST_INFO` → resubmit → `APPROVE`
  cycle would have permanently shown the stale `REQUEST_INFO` as "the"
  decision and made the review screen think no new decision could ever be
  made again. Replaced with `get_latest_decision` (used where "the current
  decision" is needed, e.g. the applicant's own status view) plus a new
  `list_decisions`/`GET /api/applications/{id}/decisions` for full history.
  The reviewer screen's "can a decision be made right now" check is now
  simply `application.status == PENDING_REVIEW`, and a "Decision history"
  section shows every past decision — satisfying the DoD's "prior review
  context retained and visible on the second review" directly, not just by
  the audit log happening to contain it.
- **Audit trail export (US-28)**: `GET
  /api/applications/{id}/audit-log/export?format=csv|json` merges the
  append-only audit trail with every recorded decision into one
  chronological view, tagged `AUDIT` or `DECISION` so a spreadsheet reader
  can filter to just the decisions. CSV is built with Python's `csv.writer`
  (never hand-joined strings), which is what actually gets commas, quotes,
  and embedded newlines in reasoning text right — verified with a
  deliberately adversarial reasoning string containing all three. A GET
  with no state-mutating side effect, verified by re-fetching the
  application before/after export and asserting nothing changed.

**Verified live, not just by tests**, via a real browser walkthrough
against running dev servers: saved a draft after only step 1, resumed it
by reference ID in a fresh page load with every field restored, completed
and submitted it (same reference ID, status flipped to `SUBMITTED`);
uploaded a document through a real `<input type="file">` (a `File` +
`DataTransfer` constructed in-page, not a mocked network call) with a
declared type; requested more information as a reviewer and confirmed the
applicant's own status view showed the reviewer's note and switched to a
"replace document" upload panel; uploaded a replacement through that same
real file-input path and watched the status flip itself back to
`PENDING_REVIEW`; approved it as a second reviewer and confirmed the
review screen showed both the earlier `REQUEST_INFO` and the later
`APPROVE` in a "Decision history" section, with the full audit trail
(including a `DOCUMENT_REPLACED` entry) in order beneath it; fetched both
the CSV and JSON exports live and confirmed the embedded comma/quote/
newline reasoning text round-tripped correctly. Confirmed a replace/upload
attempt against an already-approved application is rejected live with
`409`. Since no real extraction has run, the declared-vs-detected type
mismatch path (US-15) was exercised the same honest way Phase 3 verified
its comparison grid: a synthetic `SUCCESS` extraction was seeded directly
through the app's own `crud`/`pipeline` functions (LLM call swapped for a
fixed response, everything else real) with a deliberately mismatched
detected type — confirmed the distinct mismatch banner, the
`DECLARED_TYPE_MISMATCH` risk factor, a resulting `HIGH` risk level, and
that Approve/Reject/Request-Info all remained available (no auto-reject).
Confirmed no horizontal scrolling at a 375px mobile viewport on the review
screen. 219 backend tests pass (180 from Phases 1–5 + 39 new); a
production frontend build (`npm run build`) completes cleanly.

## Addition: reviewer login (not one of the 30 PRD stories)

**Status: Complete.** Requested and added after all 6 phases were done —
not in `docs/PRD.md`, kept deliberately small and additive: no existing
story's own domain behavior changed, only *how* a reviewer's identity is
established before acting.

- **What's protected**: `GET /api/reviewer/queue`, `POST
  /api/applications/{id}/decision`, and — closing the gap originally
  flagged here — every other reviewer-only read on an individual
  application: `GET .../extraction`, `.../risk`, `.../audit-log` (and its
  `.../audit-log/export`), and `.../decisions` (the history). A logged-in
  reviewer session (`app/auth.py`) is required for all of them; a
  decision's `reviewer_id` always comes from that session (`DecisionCreate`
  doesn't even have a `reviewer_id` field — see `app/schemas.py`), never
  from client-supplied free text. Together this closes the real gap the
  old design had: previously, anyone could both type any name into a
  reviewer-ID field *and* browse an application's full extraction,
  risk, and audit detail for any reference ID with no login at all.
- **What's still open, and why it has to be**: the bare application record
  (`GET /api/applications/{id}`), the document list, the current/singular
  decision (`GET .../decision`), and — the one that can't be closed the
  same way — the document file bytes (`GET .../documents/{id}/file`).
  These are all genuinely *shared*: the applicant's own status view
  (`ApplicationStatusPanel.jsx`) calls every one of them, unauthenticated,
  by design (applicants never log in). The document file specifically
  can't be gated behind `require_reviewer` at all without breaking
  existing, tested applicant behavior (US-06's document preview): both
  `ApplicationStatusPanel` and the reviewer's own `ReviewDetailPage` render
  it via a plain `<img>`/`<embed src>`, which cannot carry an Authorization
  header — there is no way for the browser to attach the reviewer's token
  to that request, and applicants have no token to attach at all. Locking
  that one route down would either 401 the applicant's own document
  preview (breaking US-06) or require giving applicants some form of
  credential — which contradicts "applicants continue with no login," the
  first requirement of this whole feature. This is a real, load-bearing
  exception, not an oversight — see `tests/test_reviewer_auth.py`'s
  `test_document_file_remains_unauthenticated` for the test that pins it
  down deliberately, and `test_application_record_and_document_list_remain_unauthenticated`
  for the other three shared reads.
- **How it works** (`backend/app/auth.py`, `backend/app/routers/auth.py`):
  a fixed set of demo accounts in `backend/reviewer_accounts.json`
  (committed, plaintext demo passwords, clearly marked as non-production).
  `POST /api/auth/reviewer/login` checks credentials and returns an opaque
  bearer token; sessions are an in-memory `token -> username` map with no
  expiry and no persistence — restarting the backend logs every reviewer
  out. This is a conscious simplification stated up front, not an
  oversight: CLAUDE.md's non-goals explicitly exclude production-grade
  security, and the ask was for "a simple hardcoded reviewer login... not
  a full user-management system." A real deployment would replace this
  module entirely rather than harden it in place.
- **Frontend**: `/reviewer/login` (new page), a `RequireReviewerAuth`
  guard on both reviewer routes that redirects to login with a return
  path, a reviewer-status/log-out control in the top nav, and both the
  queue page and the review detail page redirecting to login on a `401`
  (e.g. after a backend restart clears sessions). `DecisionForm` no longer
  has a free-text "Reviewer ID" field at all — it shows "Reviewing as
  `<username>`" instead, sourced from the stored session. The review
  detail page's `getExtraction`/`getAuditLog`/`getRisk`/`getDecisions`
  calls now send the reviewer's session header (a new `getJsonAsReviewer`
  helper in `api.js`, alongside the plain `getJson` the shared/applicant
  reads still use). The audit-log export needed more than a header: a
  plain `<a href>` can't carry an Authorization header either, so it's now
  fetched as a `Blob` (with the header) and saved via a throwaway
  `URL.createObjectURL` + programmatic `<a download>` click
  (`fetchAuditExport` in `api.js`) instead of linking straight to the URL.
- **Test impact, and why it was unavoidable**: 6 existing test functions
  (across `test_decisions_api.py` and `test_no_auto_approval.py`) asserted
  specific client-supplied `reviewer_id` strings, or that a missing/blank
  `reviewer_id` in the request body caused a `422` — both premises stop
  being true once identity comes from a login instead of a body field.
  These were updated to assert the equivalent new behavior (a `401`
  without a valid session; the authenticated username being what's
  recorded) rather than deleted — the underlying guarantee each test
  protects (US-24: no decision without a real reviewer identity) is
  unchanged, only the mechanism proving it is. To keep every *other*
  existing test working completely untouched, the shared test `client`
  fixture (`tests/conftest.py`) now logs in as a standard demo reviewer
  (`reviewer_1`) by default — since almost every existing test already
  used the literal string `"reviewer_1"` as its illustrative reviewer
  identity, the resulting authenticated username matches what those tests
  already asserted, so they needed no changes at all. A second demo
  account (`reviewer_2`) is available via a
  `reviewer_client()` helper for the one test that specifically needs two
  distinct reviewers in sequence (the resubmission loop).
- **New coverage**: `tests/test_reviewer_auth.py` (12 tests) — login
  success/failure, queue access with/without a session, logout actually
  invalidating a token, a decision recording the authenticated identity
  even if a different name is smuggled into the request body, two reviewer
  sessions being independent of each other, all five newly-protected reads
  rejecting an unauthenticated request (with a *nonexistent* reference ID,
  proving `require_reviewer` runs before the route even checks whether the
  application exists — a `401`, never a `404`, with no session) and
  succeeding with one, and the still-open shared endpoints (application
  record, document list, current decision, document file) explicitly
  confirmed to remain reachable with no login at all.

231 backend tests pass (227 + 4 new). Verified live: `GET
/api/reviewer/queue` returns `401` with no session and a real login
response with one; logged in as `reviewer_1` through the actual login
page, reached the queue, opened an application, submitted an Approve
decision, and confirmed both the decision history and audit log recorded
`reviewer_1` — not a typed value — as the actor; logged out and confirmed
`/reviewer` redirects back to the login page; confirmed the applicant flow
(`/`) is completely unaffected — no login prompt, no behavior change.
Confirmed no horizontal scrolling on the login page at a 375px mobile
viewport. Production frontend build passes.

**Follow-up — closing the flagged gap:** verified live via curl that all
five newly-protected reads (`extraction`, `risk`, `audit-log`,
`audit-log/export`, `decisions`) return `401` for a nonexistent reference
ID with no session, while the shared `application` and `documents` reads
correctly still return `404` (reachable, just no such application) —
confirming the auth check runs before, and independently of, whether the
application exists. In the actual browser: the applicant's own status
view loaded its document preview successfully with no login at all
(network tab: `200` on the file URL); logged in as a reviewer and
confirmed the review detail page's extraction banner, risk factors,
decision form, and audit log all loaded correctly (each request carrying
the session header); clicked both export buttons and confirmed each
triggered a real, successful (`200`) authenticated fetch; logged out and
confirmed navigating straight to `/reviewer/{reference_id}` now redirects
to the login page — the whole reviewer detail screen, not just the queue,
is unreachable without a session. 231 backend tests pass.
