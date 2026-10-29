import io

from app.llm.errors import AIUnavailableError
from app.llm.schemas import LLMExtractionResponse, LLMFieldResult
from tests.conftest import DEMO_REVIEWER_USERNAME, VALID_APPLICATION_PAYLOAD, reviewer_client

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _upload(client, reference_id, filename="id.jpg"):
    return client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": (filename, io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )


def test_full_resubmission_loop_submit_request_info_resubmit_review_approve(client):
    """US-25 DoD: "Full loop tested: submit → request info → resubmit →
    review → approve." Prior review context (the REQUEST_INFO decision)
    stays visible after the second review. Uses two distinct logged-in
    reviewer identities (app/auth.py addition) to prove the decision
    history correctly attributes each decision to whoever was actually
    logged in when they made it, not a single shared identity."""
    second_reviewer = reviewer_client("reviewer_2")

    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "PENDING_REVIEW"

    request_info = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "REQUEST_INFO", "reasoning": "Please upload a clearer photo."},
    )
    assert request_info.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "INFO_REQUESTED"

    resubmit = _upload(client, reference_id, filename="id_v2.jpg")
    assert resubmit.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "PENDING_REVIEW"

    approve = second_reviewer.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert approve.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "APPROVED"

    history = client.get(f"/api/applications/{reference_id}/decisions").json()
    assert [d["action"] for d in history] == ["REQUEST_INFO", "APPROVE"]
    assert history[0]["reviewer_id"] == DEMO_REVIEWER_USERNAME
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
        json={"action": "REQUEST_INFO", "reasoning": "Please upload a clearer photo."},
    )

    # Still INFO_REQUESTED — no resubmission yet — a second decision must be refused.
    response = client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert response.status_code == 409


def _mismatched_extraction(*args, **kwargs):
    def field(value):
        return LLMFieldResult(value=value, confidence=0.9, justification="Clearly legible.")

    return LLMExtractionResponse(
        readable=True,
        overall_justification="Document quality is good.",
        full_name=field("Someone Else"),
        date_of_birth=field(VALID_APPLICATION_PAYLOAD["date_of_birth"]),
        id_number=field(VALID_APPLICATION_PAYLOAD["id_number"]),
        document_type=field("PASSPORT"),
        expiry_date=field(None),
    )


def _resubmit_after_flagged_first_round(client, monkeypatch, second_round):
    monkeypatch.setattr("app.pipeline.run_extraction", _mismatched_extraction)
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    assert client.get(f"/api/applications/{reference_id}/extraction").json()["flag_count"] == 1

    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"action": "REQUEST_INFO", "reasoning": "Please upload a clearer photo."},
    )
    monkeypatch.setattr("app.pipeline.run_extraction", second_round)
    _upload(client, reference_id, filename="id_v2.jpg")
    return reference_id


def test_flag_count_resets_when_replacement_document_hits_ai_unavailable(client, monkeypatch):
    """A replacement document that the AI never compared must not inherit
    the previous document's mismatch count — flags describe the current
    document only, the same scoping as verification results and risk."""
    def _boom(*args, **kwargs):
        raise AIUnavailableError("simulated timeout")

    reference_id = _resubmit_after_flagged_first_round(client, monkeypatch, _boom)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["extraction"]["status"] == "AI_UNAVAILABLE"
    assert body["flag_count"] == 0
    assert client.get(f"/api/applications/{reference_id}").json()["flag_count"] == 0


def test_flag_count_resets_when_replacement_document_is_unreadable(client, monkeypatch):
    def _unreadable(*args, **kwargs):
        empty = LLMFieldResult(value=None, confidence=0.0, justification="Not legible.")
        return LLMExtractionResponse(
            readable=False,
            overall_justification="Image is blank.",
            full_name=empty,
            date_of_birth=empty,
            id_number=empty,
            document_type=empty,
            expiry_date=empty,
        )

    reference_id = _resubmit_after_flagged_first_round(client, monkeypatch, _unreadable)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["extraction"]["status"] == "UNREADABLE"
    assert body["flag_count"] == 0
