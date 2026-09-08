import io

from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _upload(client, reference_id, filename="id.jpg"):
    return client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": (filename, io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )


def test_full_resubmission_loop_submit_request_info_resubmit_review_approve(client):
    """US-25 DoD: "Full loop tested: submit → request info → resubmit →
    review → approve." Prior review context (the REQUEST_INFO decision)
    stays visible after the second review."""
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "PENDING_REVIEW"

    request_info = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "REQUEST_INFO", "reasoning": "Please upload a clearer photo."},
    )
    assert request_info.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "INFO_REQUESTED"

    resubmit = _upload(client, reference_id, filename="id_v2.jpg")
    assert resubmit.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "PENDING_REVIEW"

    approve = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_2", "action": "APPROVE"},
    )
    assert approve.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "APPROVED"

    history = client.get(f"/api/applications/{reference_id}/decisions").json()
    assert [d["action"] for d in history] == ["REQUEST_INFO", "APPROVE"]
    assert history[0]["reviewer_id"] == "reviewer_1"
    assert history[1]["reviewer_id"] == "reviewer_2"

    # GET /decision (singular) reflects the CURRENT/latest decision.
    latest = client.get(f"/api/applications/{reference_id}/decision").json()
    assert latest["action"] == "APPROVE"


def test_decision_history_empty_before_any_decision(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    response = client.get(f"/api/applications/{reference_id}/decisions")
    assert response.status_code == 200
    assert response.json() == []


def test_second_decision_blocked_until_resubmission_returns_to_pending_review(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "REQUEST_INFO", "reasoning": "Please upload a clearer photo."},
    )

    # Still INFO_REQUESTED — no resubmission yet — a second decision must be refused.
    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "APPROVE"},
    )
    assert response.status_code == 409
