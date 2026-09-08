"""Reviewer authentication (app/auth.py) — an addition on top of the PRD,
not one of the 30 user stories. Reviewer login is required for: the queue,
submitting a decision, and every reviewer-only read on an individual
application (extraction, risk, audit log — and its export, decision
history). Applicants never authenticate at all, and the endpoints they
share with the reviewer screen (the bare application record, the document
list, the current/singular decision, the document file) are deliberately
left open — see docs/PROGRESS.md's reviewer-auth addition for why the
document file specifically can't be closed the same way without breaking
applicant self-service document preview (US-06), which has no auth
mechanism of its own by design.
"""

import io

from tests.conftest import DEMO_REVIEWER_PASSWORD, DEMO_REVIEWER_USERNAME, VALID_APPLICATION_PAYLOAD, reviewer_client

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def test_login_with_valid_credentials_succeeds(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": DEMO_REVIEWER_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == DEMO_REVIEWER_USERNAME
    assert body["token"]


def test_login_with_wrong_password_fails(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_with_unknown_username_fails(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": "not_a_real_reviewer", "password": "anything"},
    )
    assert response.status_code == 401


def test_queue_requires_login(unauthenticated_client):
    response = unauthenticated_client.get("/api/reviewer/queue")
    assert response.status_code == 401


def test_queue_accessible_with_valid_login(client):
    response = client.get("/api/reviewer/queue")
    assert response.status_code == 200


def test_logout_invalidates_the_token(unauthenticated_client):
    login = unauthenticated_client.post(
        "/api/auth/reviewer/login",
        json={"username": DEMO_REVIEWER_USERNAME, "password": DEMO_REVIEWER_PASSWORD},
    )
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert unauthenticated_client.get("/api/reviewer/queue", headers=headers).status_code == 200

    logout = unauthenticated_client.post("/api/auth/reviewer/logout", headers=headers)
    assert logout.status_code == 204

    assert unauthenticated_client.get("/api/reviewer/queue", headers=headers).status_code == 401


def test_decision_uses_the_authenticated_identity_not_a_body_supplied_one(client, db_session):
    """Security property this whole feature exists for: a logged-in
    reviewer cannot impersonate a different reviewer by putting a
    different name in the request body — the DecisionCreate schema doesn't
    even have a reviewer_id field any more (see app/schemas.py), but this
    proves it even if one were smuggled in as an unrecognized extra field."""
    from app import crud

    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "APPROVE", "reviewer_id": "someone_else_entirely"},
    )
    assert response.status_code == 201
    assert response.json()["reviewer_id"] == DEMO_REVIEWER_USERNAME

    application = crud.get_application_by_reference(db_session, reference_id)
    decision = crud.get_latest_decision(db_session, application.id)
    assert decision.reviewer_id == DEMO_REVIEWER_USERNAME


def test_two_reviewer_accounts_are_independent_sessions(client):
    other = reviewer_client("reviewer_2")
    # Logging out reviewer_2's own session must not affect reviewer_1's.
    other.post("/api/auth/reviewer/logout")
    assert client.get("/api/reviewer/queue").status_code == 200


def _reach_pending_review(client) -> str:
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    return reference_id


# US-27's audit trail, US-16/US-18's risk assessment, US-09..US-14's
# extraction/verification result, and US-25's decision history are the
# reviewer-only reads closed off here — see the module docstring for what's
# deliberately still open (application record, document list, current
# decision, document file).
_PROTECTED_READ_PATHS = ["extraction", "risk", "audit-log", "audit-log/export", "decisions"]


def test_reviewer_only_reads_require_login(unauthenticated_client):
    # A nonexistent reference ID is enough — require_reviewer runs before
    # the route body would even check whether the application exists, so
    # this is 401, never 404, with no session at all.
    for path in _PROTECTED_READ_PATHS:
        response = unauthenticated_client.get(f"/api/applications/ONB-2026-99999/{path}")
        assert response.status_code == 401, f"GET .../{path} should require a reviewer login"


def test_reviewer_only_reads_accessible_with_valid_login(client):
    reference_id = _reach_pending_review(client)
    for path in _PROTECTED_READ_PATHS:
        response = client.get(f"/api/applications/{reference_id}/{path}")
        assert response.status_code in (200, 404), f"GET .../{path} should not itself be an auth failure"


def test_application_record_and_document_list_remain_unauthenticated(unauthenticated_client, client):
    """These are shared with the applicant-facing status view (which never
    logs in), so — unlike the reads above — they must NOT require a
    reviewer session."""
    reference_id = _reach_pending_review(client)
    assert unauthenticated_client.get(f"/api/applications/{reference_id}").status_code == 200
    assert unauthenticated_client.get(f"/api/applications/{reference_id}/documents").status_code == 200
    # 404 (no decision recorded yet), not 401 — proves it's reachable at all.
    assert unauthenticated_client.get(f"/api/applications/{reference_id}/decision").status_code == 404


def test_document_file_remains_unauthenticated(unauthenticated_client, client):
    """Deliberately NOT gated — see the module docstring and
    docs/PROGRESS.md: applicants view their own uploaded document through
    this same URL with no login of their own, via a plain <img>/<embed> src
    that cannot carry an Authorization header, and closing it would break
    that existing, tested behavior (US-06)."""
    reference_id = _reach_pending_review(client)
    document_id = client.get(f"/api/applications/{reference_id}/documents").json()[0]["id"]
    response = unauthenticated_client.get(f"/api/applications/{reference_id}/documents/{document_id}/file")
    assert response.status_code == 200
