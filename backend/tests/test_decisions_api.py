import io

from app import crud
from tests.conftest import DEMO_REVIEWER_USERNAME, VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _submit_and_reach_pending_review(client) -> str:
    """No ANTHROPIC_API_KEY is configured in the test environment, so this
    always degrades to AI_UNAVAILABLE (US-12) — exactly the state the review
    flow must handle correctly per this phase's instructions."""
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    return reference_id


def test_approve_requires_no_reasoning(client):
    reference_id = _submit_and_reach_pending_review(client)
    response = client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert response.status_code == 201
    assert response.json()["action"] == "APPROVE"
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "APPROVED"


def test_reject_without_reasoning_is_rejected_by_api(client):
    reference_id = _submit_and_reach_pending_review(client)
    response = client.post(f"/api/applications/{reference_id}/decision", json={"action": "REJECT"})
    assert response.status_code == 422


def test_reject_with_blank_reasoning_is_rejected_by_api(client):
    reference_id = _submit_and_reach_pending_review(client)
    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "REJECT", "reasoning": "   "},
    )
    assert response.status_code == 422


def test_reject_with_reasoning_succeeds(client):
    reference_id = _submit_and_reach_pending_review(client)
    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "REJECT", "reasoning": "ID number does not match."},
    )
    assert response.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "REJECTED"


def test_request_info_without_reasoning_is_rejected(client):
    reference_id = _submit_and_reach_pending_review(client)
    response = client.post(f"/api/applications/{reference_id}/decision", json={"action": "REQUEST_INFO"})
    assert response.status_code == 422


def test_request_info_with_reasoning_succeeds(client):
    reference_id = _submit_and_reach_pending_review(client)
    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "REQUEST_INFO", "reasoning": "Please upload a clearer document."},
    )
    assert response.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "INFO_REQUESTED"


def test_decision_cannot_be_submitted_twice(client):
    """US-23 DoD: prevented server-side, not just by disabling a button."""
    reference_id = _submit_and_reach_pending_review(client)
    first = client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert first.status_code == 201

    second = client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert second.status_code == 409
    # The original decision must be untouched.
    assert client.get(f"/api/applications/{reference_id}/decision").json()["reviewer_id"] == DEMO_REVIEWER_USERNAME


def test_decision_requires_reviewer_login(unauthenticated_client, client):
    """Addition on top of the PRD (app/auth.py): US-24's "attempting to
    approve without reviewer identity fails" is now enforced by requiring a
    logged-in reviewer session, not a free-text reviewer_id field."""
    reference_id = _submit_and_reach_pending_review(client)
    response = unauthenticated_client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert response.status_code == 401


def test_decision_rejects_invalid_bearer_token(unauthenticated_client, client):
    reference_id = _submit_and_reach_pending_review(client)
    response = unauthenticated_client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "APPROVE"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_decision_on_unknown_application_returns_404(client):
    response = client.post("/api/applications/ONB-2026-99999/decision", json={"action": "APPROVE"})
    assert response.status_code == 404


def test_decision_on_application_not_yet_pending_review_is_rejected(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    # No document uploaded yet — still SUBMITTED, not PENDING_REVIEW.
    response = client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert response.status_code == 409


def test_decision_writes_audit_entry_with_reviewer_identity_and_reasoning(client, db_session):
    reference_id = _submit_and_reach_pending_review(client)
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "REJECT", "reasoning": "Blurry document."},
    )
    application = crud.get_application_by_reference(db_session, reference_id)
    entries = crud.list_audit_log_entries(db_session, application.id)
    decision_entries = [e for e in entries if e.action.startswith("DECISION_")]
    assert len(decision_entries) == 1
    assert decision_entries[0].actor == DEMO_REVIEWER_USERNAME
    assert decision_entries[0].action == "DECISION_REJECT"
    assert "Blurry document." in decision_entries[0].details


def test_get_decision_returns_recorded_decision(client):
    reference_id = _submit_and_reach_pending_review(client)
    client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    response = client.get(f"/api/applications/{reference_id}/decision")
    assert response.status_code == 200
    assert response.json()["action"] == "APPROVE"
    assert response.json()["reviewer_id"] == DEMO_REVIEWER_USERNAME


def test_get_decision_404_before_any_decision(client):
    reference_id = _submit_and_reach_pending_review(client)
    response = client.get(f"/api/applications/{reference_id}/decision")
    assert response.status_code == 404
