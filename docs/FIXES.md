# Fixes

Every bug and documentation error fixed in OnboardIQ that the repository
can evidence, with where the evidence is and how the problem was found.
Items are listed only when a commit, a diff or `docs/PROGRESS.md` shows
that the problem existed and was fixed.

**Totals: 11 bugs and 1 documentation error fixed, plus 1 known gap.**

"How found" uses what the evidence says: *running the app* (caught by
using the app, not by an automated test), *review* (found while
implementing or auditing), or *unknown* (the evidence does not say).

## Bugs fixed

| # | What was wrong | Evidence | How found |
|---|---|---|---|
| 1 | A replacement document that ended up `AI_UNAVAILABLE` or `UNREADABLE` kept the previous document's mismatch count | `656e8ba`; two tests in `tests/test_resubmission_loop.py` | Running the app (while reviewing the demo recordings; the commit message does not say) |
| 2 | "Back to queue" was a plain route link that dropped the reviewer's queue filters | `b2e28cd` commit body; `PROGRESS.md` Phase 4 | Running the app |
| 3 | The seeded demo ID image passed the file-type check but did not decode in a browser | `c71f230`; `PROGRESS.md` "Demo seed script" | Running the app |
| 4 | After a request-info, resubmit and approve cycle, the first (stale) decision was shown as the current one | `68ec999` commit body; `PROGRESS.md` Phase 6 (`get_latest_decision`) | Review |
| 5 | Anyone could attribute a decision to any typed reviewer name | `f47453b` commit body | Review |
| 6 | Verification results had no link to their document, so a resubmission's results piled up with an earlier round's | `68ec999` commit body; `PROGRESS.md` Phase 6 | Review |
| 7 | Reviewer-only reads (extraction, risk, audit log and export, decision history) needed no login | `40b4ea2`; `PROGRESS.md` "Addition: reviewer login" | Review |
| 8 | The policy assistant's retrieval log was silently discarded because no log level was configured | `81e8572` commit body; `PROGRESS.md` Phase 5 | Running the app |
| 9 | "Back to queue" was missing while a review page was loading or had failed to load | `289d4e7` diff of `ReviewDetailPage.jsx`; `PROGRESS.md` "Nav bar polish" | Unknown |
| 10 | The stats bar's "Overdue" count read as a sixth total instead of a subset of Pending | `e37550a`; `PROGRESS.md` "Overdue label fix" | Unknown |
| 11 | The OnboardIQ logo sent a logged-in reviewer to the applicant form | `0f0ebea` | Unknown |

## Documentation error fixed

| # | What was wrong | Evidence | How found |
|---|---|---|---|
| 12 | The README's status line still described Phase 3 after Phase 4 had landed | `77af0a3` (changes `README.md` only; "found during a full Phases 1-4 audit") | Review |

## Known gap (documented, not fixed)

| What | Evidence |
|---|---|
| The intake form's email check accepts a few malformed shapes that the server's `EmailStr` rejects; such values are caught only at final submission | `PROGRESS.md` "Inline field validation"; README "Known limitations" |

## Not counted

- **Drafts and the submission rate limit.** `537971a` added rate limiting
  and covered the draft endpoints in the same commit, so no released
  version had the gap. It is a design decision, not a fixed bug.
