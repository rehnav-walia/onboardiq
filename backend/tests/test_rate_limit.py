"""Unit tests for the SlidingWindowRateLimiter itself (app/rate_limit.py)
— an addition on top of the PRD, not one of the 30 user stories. These
test the class directly, independent of the two app-wide instances or any
HTTP endpoint, using a monkeypatched clock so "resets after the window"
can be verified without a real sleep.
"""

from app.rate_limit import SlidingWindowRateLimiter


def test_allows_up_to_max_hits_within_window():
    limiter = SlidingWindowRateLimiter(max_hits=3, window_seconds=60)
    for _ in range(3):
        assert limiter.retry_after("k") is None
        limiter.record("k")
    # The 4th would be over the limit.
    assert limiter.retry_after("k") is not None


def test_blocks_after_max_hits_with_positive_retry_after():
    limiter = SlidingWindowRateLimiter(max_hits=2, window_seconds=60)
    limiter.record("k")
    limiter.record("k")
    retry_after = limiter.retry_after("k")
    assert retry_after is not None
    assert 0 < retry_after <= 60


def test_different_keys_are_independent():
    limiter = SlidingWindowRateLimiter(max_hits=1, window_seconds=60)
    limiter.record("ip-a")
    assert limiter.retry_after("ip-a") is not None
    # A different key (e.g. a different client IP) has never hit this
    # limiter and must not be affected by ip-a's state.
    assert limiter.retry_after("ip-b") is None


def test_reset_clears_state_immediately():
    limiter = SlidingWindowRateLimiter(max_hits=1, window_seconds=60)
    limiter.record("k")
    assert limiter.retry_after("k") is not None
    limiter.reset("k")
    assert limiter.retry_after("k") is None


def test_clear_all_resets_every_key():
    limiter = SlidingWindowRateLimiter(max_hits=1, window_seconds=60)
    limiter.record("a")
    limiter.record("b")
    limiter.clear_all()
    assert limiter.retry_after("a") is None
    assert limiter.retry_after("b") is None


def test_resets_after_window_expires(monkeypatch):
    """The core "does the limit actually reset over time" behavior —
    verified deterministically via a monkeypatched clock rather than a
    real sleep."""
    fake_now = [1000.0]
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: fake_now[0])

    limiter = SlidingWindowRateLimiter(max_hits=2, window_seconds=10)
    limiter.record("k")
    limiter.record("k")
    assert limiter.retry_after("k") is not None

    # Still inside the window.
    fake_now[0] += 9.9
    assert limiter.retry_after("k") is not None

    # Now past the window — both old hits have aged out.
    fake_now[0] += 0.2
    assert limiter.retry_after("k") is None

    # And a fresh hit is accepted again, restarting the window.
    limiter.record("k")
    assert limiter.retry_after("k") is None
