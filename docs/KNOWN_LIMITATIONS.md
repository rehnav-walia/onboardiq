# Known limitations (full technical detail)

Moved unchanged from the README, which now keeps a one-line summary of
each; where the text says "above", it means a section of the README.

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

## Added after the move

- **Frontend dependency advisories (`npm audit`, run 2026-10-31 against
  `frontend/package-lock.json`).** 5 advisories: 2 high, 3 moderate, 0
  critical.
  - Development tooling only (the Vite dev server and build, not shipped
    to the browser): `vite` 5.4.21 (high), `source-map-js` 1.2.1 (high,
    pulled in by Vite through `postcss`), and `esbuild` 0.21.5 (moderate).
    The `vite` and `esbuild` fixes need a major upgrade to Vite 8;
    `source-map-js` has a fix within its current range.
  - Shipped with the app: `react-router` and `react-router-dom` 6.30.6
    (moderate; an open redirect via a backslash in `<Link>` or
    `useNavigate`, and an issue in server-side-rendering hydration, which
    this app does not use). The fix needs a major upgrade to React
    Router 7.
