# AI-Powered Banking Onboarding Application

## READ FIRST
**Always read `docs/PRD.md` before implementing anything.** It contains 10 features
and 30 user stories (US-01 to US-30), each with Acceptance Criteria and a Definition of Done.
Implement against story IDs. Do not invent requirements not in the PRD — if something is
missing or ambiguous, ask before assuming.

## Project Context
Portfolio / campus-placement project demonstrating "domain + AI infusion" in banking.
Core thesis: AI extracts, compares, and explains — a human validates and approves.

## Non-Negotiable Design Principles
1. **No auto-approval.** No code path may set an application to `APPROVED` without a
   recorded human reviewer decision. See US-24 — this must be provable by an automated test.
2. **No unexplained AI output.** Every extraction and comparison result must carry a
   plain-language justification before it can render in the UI. See US-26.
3. **Append-only audit.** Audit entries have no update or delete path. See US-27.
4. **Graceful degradation.** If the LLM fails, route to manual review — never error out
   to the applicant. See US-12.

## Tech Stack
- Backend: FastAPI (Python) — chosen for AI/RAG ecosystem fit
- Frontend: React
- Database: SQLite for local dev (keep the data layer swappable)
- Vector store: Chroma (local, no external service required)
- LLM: Anthropic API via official SDK

## Conventions
- Prompts live in a dedicated `prompts/` directory as named templates — never inline strings
- Thresholds, timeouts, and model names come from environment config, never hardcoded
- Every new logic module gets unit tests in the same commit
- Build one vertical slice end-to-end before starting the next (see PRD section 12)

## Working Agreement
- Implement one phase at a time from the PRD build sequence
- When a story is complete, state which AC and DoD items are satisfied and which are not
- Flag any AC that cannot be met as specified rather than silently skipping it

## Out of Scope
Insurance, lending, collections, voice agents, real ID-verification APIs,
production-grade security. Mock where needed and note as future scope in the README.
