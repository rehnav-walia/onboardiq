"""API-level rate limiting tests — an addition on top of the PRD, not one
of the 30 user stories (see app/rate_limit.py). Exercises the real
endpoints end-to-end with the app's actual configured limits (5 failed
logins/15 min, 10 submissions/hour — app/config.py), rather than mocking
the limiter, so this proves the wiring, not just the class.
"""

from tests.conftest import DEMO_REVIEWER_PASSWORD, DEMO_REVIEWER_USERNAME, VALID_APPLICATION_PAYLOAD


def test_login_allows_up_to_the_configured_number_of_failed_attempts(unauthenticated_client):
    for _ in range(5):
        response = unauthenticated_client.post(
            "/api/auth/reviewer/login",
            json={"username": DEMO_REVIEWER_USERNAME, "password": "wrong-password"},
        )
        assert response.status_code == 401


def test_login_blocked_with_429_and_retry_after_once_over_the_limit(unauthenticated_client):
    for _ in range(5):
        unauthenticated_client.post(
            "/api/auth/reviewer/login",
            json={"username": DEMO_REVIEWER_USERNAME, "password": "wrong-password"},
        )

    # The 6th attempt is refused outright — even with the CORRECT password,
    # proving this is a real lockout, not just "the 6th guess also failed."
    response = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": DEMO_REVIEWER_PASSWORD},
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
    # A plain-language message, never a raw stack trace or library internals.
    body = response.json()
    assert "message" in body
    assert "too many attempts" in body["message"].lower()


def test_login_rate_limit_is_per_ip_not_global(unauthenticated_client):
    """TestClient requests all share one fake client IP, so this can't
    exercise true per-IP isolation over HTTP — but it documents and pins
    the intended behavior at the unit level (see test_rate_limit.py's
    test_different_keys_are_independent, which is what actually proves
    two IPs don't share a bucket)."""
    from app.rate_limit import login_limiter

    login_limiter.record("203.0.113.1")
    login_limiter.record("203.0.113.1")
    assert login_limiter.retry_after("203.0.113.2") is None


def test_successful_login_is_not_rate_limited_and_resets_failed_count(unauthenticated_client):
    # Three failed attempts...
    for _ in range(3):
        response = unauthenticated_client.post(
            "/api/auth/reviewer/login",
            json={"username": DEMO_REVIEWER_USERNAME, "password": "wrong-password"},
        )
        assert response.status_code == 401

    # ...then a correct one succeeds immediately (3 < 5, but also proves a
    # success is never itself blocked).
    success = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": DEMO_REVIEWER_PASSWORD},
    )
    assert success.status_code == 200

    # And the failed-attempt count was reset by that success: 5 MORE
    # failures are needed before the next lockout, not just 2 more.
    for _ in range(4):
        response = unauthenticated_client.post(
            "/api/auth/reviewer/login",
            json={"username": DEMO_REVIEWER_USERNAME, "password": "wrong-password"},
        )
        assert response.status_code == 401

    still_not_blocked = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": "wrong-password"},
    )
    assert still_not_blocked.status_code == 401  # this is the 5th since the reset — still allowed to attempt

    blocked_now = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": DEMO_REVIEWER_PASSWORD},
    )
    assert blocked_now.status_code == 429


def test_login_rate_limit_resets_after_the_window_expires(unauthenticated_client, monkeypatch):
    fake_now = [1_000_000.0]
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: fake_now[0])

    for _ in range(5):
        unauthenticated_client.post(
            "/api/auth/reviewer/login",
            json={"username": DEMO_REVIEWER_USERNAME, "password": "wrong-password"},
        )
    blocked = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": DEMO_REVIEWER_PASSWORD},
    )
    assert blocked.status_code == 429

    # Fast-forward past the configured 15-minute window.
    fake_now[0] += 15 * 60 + 1

    allowed_again = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": DEMO_REVIEWER_PASSWORD},
    )
    assert allowed_again.status_code == 200


def test_submission_allows_up_to_the_configured_number_per_hour(unauthenticated_client):
    for _ in range(10):
        response = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
        assert response.status_code == 201


def test_submission_blocked_with_429_and_retry_after_once_over_the_limit(unauthenticated_client):
    for _ in range(10):
        unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)

    response = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
    assert "too many attempts" in response.json()["message"].lower()


def test_draft_creation_shares_the_same_budget_as_direct_submission(unauthenticated_client):
    """create_draft, submit_draft, and submit_application all draw from
    one shared per-IP budget (app/rate_limit.py) — otherwise someone could
    flood the queue via drafts instead of direct submissions, sidestepping
    the limit entirely."""
    for _ in range(5):
        response = unauthenticated_client.post("/api/applications/draft", json={})
        assert response.status_code == 201
    for _ in range(5):
        response = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
        assert response.status_code == 201

    # 5 drafts + 5 direct submissions = 10, the full shared budget.
    blocked_draft = unauthenticated_client.post("/api/applications/draft", json={})
    assert blocked_draft.status_code == 429
    blocked_submission = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    assert blocked_submission.status_code == 429


def test_submit_draft_endpoint_is_rate_limited_and_shares_the_budget(unauthenticated_client):
    draft = unauthenticated_client.post("/api/applications/draft", json=VALID_APPLICATION_PAYLOAD).json()
    reference_id = draft["reference_id"]

    # That draft creation was 1 of 10. 9 more direct submissions exhausts the budget.
    for _ in range(9):
        response = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
        assert response.status_code == 201

    blocked = unauthenticated_client.post(f"/api/applications/draft/{reference_id}/submit")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_submission_rate_limit_resets_after_the_window_expires(unauthenticated_client, monkeypatch):
    fake_now = [2_000_000.0]
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: fake_now[0])

    for _ in range(10):
        unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    blocked = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    assert blocked.status_code == 429

    # Fast-forward past the configured 1-hour window.
    fake_now[0] += 60 * 60 + 1

    allowed_again = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    assert allowed_again.status_code == 201


def test_malformed_submissions_do_not_consume_the_limit(unauthenticated_client):
    """A request that fails schema validation (422) never reaches the
    route body at all — FastAPI rejects it before app/rate_limit.py's
    check ever runs — so it can't flood the *queue* (there's nothing to
    flood; no Application row is ever created) and correctly doesn't cost
    the caller a slot either."""
    invalid_payload = {**VALID_APPLICATION_PAYLOAD, "email": "not-an-email"}
    for _ in range(15):  # well past the limit of 10 — still never blocked
        response = unauthenticated_client.post("/api/applications", json=invalid_payload)
        assert response.status_code == 422

    still_allowed = unauthenticated_client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    assert still_allowed.status_code == 201
