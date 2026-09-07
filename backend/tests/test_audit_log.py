import io

from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def test_full_lifecycle_produces_a_complete_ordered_audit_trail(client):
    """US-27 DoD: a full application lifecycle produces a complete,
    correctly ordered trail. No ANTHROPIC_API_KEY is configured in the
    test environment, so extraction degrades to AI_UNAVAILABLE (US-12) —
    exactly the scenario this phase is instructed to handle correctly."""
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "APPROVE"},
    )

    response = client.get(f"/api/applications/{reference_id}/audit-log")
    assert response.status_code == 200
    entries = response.json()
    actions = [e["action"] for e in entries]

    assert actions == [
        "APPLICATION_SUBMITTED",
        "PROCESSING_STARTED",
        "EXTRACTION_FAILED",
        "DECISION_APPROVE",
    ]

    timestamps = [e["timestamp"] for e in entries]
    assert timestamps == sorted(timestamps)

    for entry in entries:
        assert entry["actor"], "every entry must record who/what performed the action"
        assert entry["details"], "every entry must carry a human-readable reason"


def test_audit_log_on_successful_extraction_includes_verification_completed(client, monkeypatch):
    from app.llm.schemas import LLMExtractionResponse, LLMFieldResult

    def _field(value):
        return LLMFieldResult(value=value, confidence=0.9, justification="Clearly legible.")

    def _fake_response(*args, **kwargs):
        return LLMExtractionResponse(
            readable=True,
            overall_justification="Good quality.",
            full_name=_field("Jane Doe"),
            date_of_birth=_field("1990-05-15"),
            id_number=_field("A1234567"),
            document_type=_field("PASSPORT"),
        )

    monkeypatch.setattr("app.pipeline.run_extraction", _fake_response)
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    actions = [e["action"] for e in client.get(f"/api/applications/{reference_id}/audit-log").json()]
    assert actions == [
        "APPLICATION_SUBMITTED",
        "PROCESSING_STARTED",
        "EXTRACTION_SUCCEEDED",
        "VERIFICATION_COMPLETED",
    ]


def test_audit_log_has_no_update_or_delete_endpoint(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    assert client.put(f"/api/applications/{reference_id}/audit-log", json={}).status_code == 405
    assert client.delete(f"/api/applications/{reference_id}/audit-log").status_code == 405


def test_audit_log_for_unknown_application_returns_404(client):
    response = client.get("/api/applications/ONB-2026-99999/audit-log")
    assert response.status_code == 404
