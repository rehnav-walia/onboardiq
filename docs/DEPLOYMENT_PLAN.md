# v1.1 public demo plan (not built)

Status: a plan only. Nothing in this document is implemented in v1.0.
File references point at the v1.0 code that each item would change.

## Recommended shape: a reviewer-only public demo

- A `DEMO_MODE` setting turns the public instance into a reviewer-only
  demo.
- In demo mode the endpoints that let a visitor create or change
  applicant data return `403` with a plain-language message:
  - `POST /api/applications` (direct submission)
  - `POST /api/applications/draft` and
    `PATCH /api/applications/draft/{reference_id}` (drafts)
  - `POST /api/applications/draft/{reference_id}/submit`
  - `POST /api/applications/{reference_id}/documents` (upload)

  The first four live in `backend/app/routers/applications.py`, the
  upload in `backend/app/routers/documents.py`.
- The applicant pages in the frontend show a short "Submission is
  disabled in this demo" notice instead of the form and upload panel.
- Visitors log in as a demo reviewer and work through the seeded
  applications (`backend/seed_demo.py --full`): read the comparison and
  risk breakdown, approve, reject or request more information, and export
  the audit trail.

## Hosting

- One Docker container on a free host, serving both the API and the
  built frontend (`frontend/dist`) from FastAPI, so there is one origin:
  no CORS configuration and no separate frontend deployment.
- Exactly one uvicorn worker, because sessions and rate limits are held
  in process memory (`backend/app/auth.py`, `backend/app/rate_limit.py`).
- An ephemeral disk is acceptable and even convenient: the demo resets to
  seeded data anyway, so nothing needs to survive a restart.
- No `ANTHROPIC_API_KEY` on the host. AI results stay simulated, as the
  demo page already states.
- Candidate hosts, their prices, free-tier limits (RAM, CPU, monthly
  hours), sleep-after-idle behaviour and cold-start times:
  **UNVERIFIED - check the host's pricing page** before choosing. This
  includes any figure quoted in conversation while planning.
- Bake the policy assistant's local embedding model into the image, so a
  cold start doesn't download it again (it is loaded through Chroma's
  default embedding function in `backend/app/rag/store.py`). Its
  download size is **UNVERIFIED**.

## Needed work

1. **Demo reviewer accounts from environment variables.** `_load_accounts`
   in `backend/app/auth.py` reads `backend/reviewer_accounts.json` today.
   In demo mode it would read the accounts from a host environment
   variable, and the committed file would be left out of the image.
2. **Proxy-IP handling for rate limits.** `client_ip` in
   `backend/app/rate_limit.py` uses the socket's peer address, which
   behind a hosting proxy is the proxy, so all visitors would share one
   budget. Start uvicorn with proxy headers trusted only from the host's
   own proxy.
3. **Reset to seeded data on restart and on a schedule.**
   - On restart: the container entrypoint deletes the database and the
     storage folder, runs `seed_demo.py --full`, then starts the server.
   - On a schedule (for example every one to two hours): an in-process
     task drops and recreates the tables, clears the storage folder,
     reseeds, and clears the in-memory sessions and rate limiters.
   - Do not call `seed_demo.py --reset` against a running server: on Linux
     deleting the open SQLite file succeeds, but the running process keeps
     using the deleted file, so the reset would not take effect until the
     next restart.
4. **"Demo environment" banner with a collapsible demo-access box.**
   - The banner states that everything is sample data and resets on a
     schedule.
   - The demo-access box shows the demo reviewer credentials, served by
     the backend from the same environment variable as item 1.
   - The hard-coded hint on the login page
     (`frontend/src/pages/ReviewerLoginPage.jsx`) uses the same source.
5. **Cap on reasoning length.** `DecisionCreate.reasoning` in
   `backend/app/schemas.py` has no maximum today; cap it (for example 500
   characters).
6. **`/docs` disabled.** The FastAPI app in `backend/app/main.py` exposes
   the interactive API docs by default; turn them off in demo mode.

## Out of scope

- Persistent storage (scheduled resets make it unnecessary)
- Real authentication or per-visitor accounts
- Multiple workers or instances
- A custom domain
- A live AI key

## Biggest risk: strangers entering real personal data

- **Why it matters in v1.0:** reference IDs are sequential
  (`_generate_reference_id` in `backend/app/crud.py`), and the
  application record and document files are readable without a login
  (`backend/app/routers/applications.py`,
  `backend/app/routers/documents.py`). On a public instance, anything one
  visitor typed or uploaded could be read by another.
- **How the reviewer-only shape removes it:** with every applicant
  submission and upload endpoint disabled, no visitor can create an
  application or upload a file. The only applications on the instance
  are the seeded sample ones, so the open reads expose only made-up data.
- **What remains, and how it is contained:**
  - Decision reasoning is still free text typed by visitors. It is
    capped (item 5) and wiped at every reset, but it is not private:
    the current decision, reasoning included, is one of the open reads
    (`GET /api/applications/{reference_id}/decision` in
    `backend/app/routers/applications.py`), and every visitor shares the
    same demo reviewer login. The banner should say not to type personal
    details anywhere.
  - The policy assistant still accepts a question, and
    `backend/app/rag/assistant.py` writes the question text to the server
    log. Either disable the assistant in demo mode or stop logging the
    question text there.

## Effort estimate

A rough guess, not a measured figure: **about 10-16 hours** for items 1-6
plus the demo-mode switches, the Dockerfile, and a deploy and smoke test.
