import io

from app.llm.errors import AIUnavailableError
from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _upload(client, reference_id):
    return client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )


def test_high_risk_application_can_still_be_approved(client, monkeypatch):
    """US-18 AC/DoD: risk is advisory only — a HIGH risk application must
    still be approvable by a human. Engineered to reach HIGH deterministically
    by combining an under-minimum-age applicant with AI_UNAVAILABLE."""
    monkeypatch.setattr(
        "app.pipeline.run_extraction",
        lambda *a, **k: (_ for _ in ()).throw(AIUnavailableError("simulated outage")),
    )
    payload = dict(VALID_APPLICATION_PAYLOAD, date_of_birth="2020-01-01", email="minor.applicant@example.com")
    reference_id = client.post("/api/applications", json=payload).json()["reference_id"]
    _upload(client, reference_id)

    risk = client.get(f"/api/applications/{reference_id}/risk").json()
    assert risk["risk_level"] == "HIGH"
    assert len(risk["factors"]) >= 2  # AI_UNAVAILABLE + UNDER_MINIMUM_AGE

    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "APPROVE"},
    )
    assert response.status_code == 201

    application = client.get(f"/api/applications/{reference_id}").json()
    assert application["status"] == "APPROVED"
    assert application["risk_level"] == "HIGH"  # the approval doesn't erase or hide the score


def test_risk_endpoint_for_unknown_application_returns_404(client):
    response = client.get("/api/applications/ONB-2026-99999/risk")
    assert response.status_code == 404
