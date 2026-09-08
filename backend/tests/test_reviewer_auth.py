"""Reviewer authentication (app/auth.py) — an addition on top of the PRD,
not one of the 30 user stories. Deliberately small in scope: queue access
and decision submission require a logged-in reviewer session; applicants
never authenticate at all.
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
