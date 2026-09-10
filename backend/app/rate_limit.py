"""Minimal in-memory rate limiting — an addition on top of the PRD, not
one of the 30 user stories. A single sliding-window-log per key (e.g. a
client IP), held in process memory: no Redis or other external
infrastructure, appropriate for a single-instance demo/local app
(CLAUDE.md's non-goals explicitly exclude production-grade security). It
resets whenever the backend restarts and is not shared across worker
processes or machines — a real multi-instance deployment would need a
shared store instead.

Not perfectly atomic under concurrent requests from the same key: checking
whether a key is currently blocked (retry_after) and recording a hit
(record) are two separate lock-protected steps, not one compare-and-swap.
A burst of simultaneous requests from the same IP could briefly overshoot
the limit by a few. That's an accepted tradeoff for this project's stated
scope, not an oversight — a production rate limiter needs an atomic
check-and-increment (e.g. Redis' INCR + EXPIRE), which is exactly the kind
of external infrastructure this module is deliberately avoiding.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings


class SlidingWindowRateLimiter:
    def __init__(self, max_hits: int, window_seconds: float):
        self._max_hits = max_hits
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> None:
        # Caller already holds self._lock.
        q = self._hits[key]
        cutoff = now - self._window_seconds
        while q and q[0] <= cutoff:
            q.popleft()

    def retry_after(self, key: str) -> float | None:
        """None if a new hit for `key` would be allowed right now;
        otherwise the number of seconds until the oldest hit in the
        current window ages out and a slot frees up."""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            q = self._hits[key]
            if len(q) < self._max_hits:
                return None
            return max(self._window_seconds - (now - q[0]), 0.0)

    def record(self, key: str) -> None:
        """Records one hit against `key`. Callers are expected to check
        retry_after() first — this method itself doesn't refuse hits, so
        it's also usable to unconditionally log an event (e.g. a failed
        login attempt) regardless of whether that specific hit was over
        the limit."""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._hits[key].append(now)

    def reset(self, key: str) -> None:
        """Clears every recorded hit for `key` — e.g. a successful login
        forgives that IP's prior failed attempts rather than leaving it
        partway toward a lockout it no longer deserves."""
        with self._lock:
            self._hits.pop(key, None)

    def clear_all(self) -> None:
        """Wipes every key's state. Application code never calls this —
        it exists for test isolation, since the module-level limiter
        instances below are process-wide singletons (see tests/conftest.py's
        autouse _reset_rate_limiters fixture)."""
        with self._lock:
            self._hits.clear()


_settings = get_settings()

# US-24-adjacent hardening, not a PRD story: only FAILED login attempts
# count against this limit (see routers/auth.py) — a correct password
# always gets in immediately, and a successful login resets the count, so
# a legitimate reviewer who mistypes their password a couple of times is
# never locked out of their own account.
login_limiter = SlidingWindowRateLimiter(
    max_hits=_settings.login_rate_limit_max_attempts,
    window_seconds=_settings.login_rate_limit_window_seconds,
)

# Every submission attempt counts here, successful or not — this guards
# the reviewer queue against being flooded with rows, not against
# credential guessing, so there's no reason to special-case failures.
application_limiter = SlidingWindowRateLimiter(
    max_hits=_settings.application_rate_limit_max_submissions,
    window_seconds=_settings.application_rate_limit_window_seconds,
)


def client_ip(request: Request) -> str:
    """Best-effort client identifier for rate limiting. `request.client`
    is None in some ASGI test/proxy setups — falls back to a shared
    bucket rather than crashing; that just means those requests share one
    limiter slot instead of being split per-IP, which is acceptable for
    local/demo use (see this module's docstring)."""
    return request.client.host if request.client else "unknown"


def enforce(limiter: SlidingWindowRateLimiter, key: str) -> None:
    """Raises a 429 with a Retry-After header (and a plain-language
    message, never a stack trace) if `key` is currently over the limit.
    Does not itself record a hit — callers decide when a hit counts (see
    the login vs. application-submission limiters above)."""
    retry_after = limiter.retry_after(key)
    if retry_after is not None:
        retry_after_seconds = int(retry_after) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Please try again in {retry_after_seconds} second(s).",
            headers={"Retry-After": str(retry_after_seconds)},
        )
