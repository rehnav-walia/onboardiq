"""Minimal reviewer authentication.

This is an addition on top of the PRD (which does not specify a login
system) — deliberately small in scope:

- A fixed set of reviewer accounts loaded from a JSON config file
  (`reviewer_accounts.json`), not a database table — no signup, no password
  reset, no roles beyond "reviewer". Applicants never authenticate at all;
  nothing in this module is reachable from any applicant-facing route.
- Sessions are an in-memory token -> username map. There is no persistence,
  no expiry, and no hashing of the demo passwords. This is a conscious
  simplification, not an oversight — CLAUDE.md's non-goals explicitly
  exclude production-grade security for this project. A real deployment
  would replace this module entirely (e.g. a proper identity provider),
  not extend it.
"""

import json
import secrets
from pathlib import Path
from threading import Lock

from fastapi import Header, HTTPException

from app.config import get_settings

# token -> username. Module-level and in-memory by design (see docstring) —
# restarting the server logs every reviewer out, which is an accepted
# limitation for a portfolio project.
_sessions: dict[str, str] = {}
_lock = Lock()


def _load_accounts() -> dict[str, dict]:
    path = Path(get_settings().reviewer_accounts_file)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("accounts", {})


def authenticate(username: str, password: str) -> str | None:
    """Returns a new bearer token on success, None on bad credentials."""
    account = _load_accounts().get(username)
    if account is None or account.get("password") != password:
        return None
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = username
    return token


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :].strip()
    return token or None


def logout(authorization: str | None) -> None:
    token = extract_bearer_token(authorization)
    if token:
        with _lock:
            _sessions.pop(token, None)


def require_reviewer(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency for reviewer-only routes (queue access, submitting
    a decision — the scope this feature was asked to cover). Returns the
    authenticated reviewer's username, which callers use as the decision's
    `reviewer_id` instead of trusting a client-supplied free-text field."""
    token = extract_bearer_token(authorization)
    username = _sessions.get(token) if token else None
    if username is None:
        raise HTTPException(status_code=401, detail="Reviewer login required.")
    return username
