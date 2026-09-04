from datetime import date, timedelta

from tests.conftest import VALID_APPLICATION_PAYLOAD


def test_submit_application_success(client):
    response = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "SUBMITTED"
    assert body["reference_id"].startswith(f"ONB-{date.today().year}-")
    assert body["full_name"] == VALID_APPLICATION_PAYLOAD["full_name"]


def test_reference_ids_are_unique_across_submissions(client):
    first = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()
    second = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()
    assert first["reference_id"] != second["reference_id"]


def test_get_application_by_reference_id(client):
    created = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()
    response = client.get(f"/api/applications/{created['reference_id']}")
    assert response.status_code == 200
    assert response.json()["reference_id"] == created["reference_id"]


def test_get_unknown_reference_id_returns_clean_404(client):
    response = client.get("/api/applications/ONB-2026-99999")
    assert response.status_code == 404
    assert "message" in response.json()
    assert "Traceback" not in response.text


def test_missing_required_field_rejected_with_field_message(client):
    payload = {**VALID_APPLICATION_PAYLOAD, "full_name": ""}
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert "full_name" in body["errors"]
    assert "required" in body["errors"]["full_name"].lower()
    # US-04 DoD: no raw pydantic/library internals should reach the client.
    assert "loc" not in body
    assert "ctx" not in str(body)


def test_invalid_email_rejected_with_specific_message(client):
    payload = {**VALID_APPLICATION_PAYLOAD, "email": "not-an-email"}
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 422
    assert "email" in response.json()["errors"]


def test_invalid_phone_rejected_with_specific_message(client):
    payload = {**VALID_APPLICATION_PAYLOAD, "phone": "123"}
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 422
    assert "phone" in response.json()["errors"]


def test_future_date_of_birth_rejected_with_specific_message(client):
    future_dob = (date.today() + timedelta(days=1)).isoformat()
    payload = {**VALID_APPLICATION_PAYLOAD, "date_of_birth": future_dob}
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 422
    assert "future" in response.json()["errors"]["date_of_birth"].lower()


def test_invalid_account_type_rejected(client):
    payload = {**VALID_APPLICATION_PAYLOAD, "account_type": "CRYPTO"}
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 422


def test_server_side_validation_cannot_be_bypassed_by_crafted_request(client):
    """US-01 DoD: a direct API call that skips the browser entirely — and
    tries to set server-controlled fields — still gets validated, and
    fields the schema doesn't expose are silently ignored rather than
    trusted."""
    payload = {
        **VALID_APPLICATION_PAYLOAD,
        "email": "still-not-an-email",
        "status": "APPROVED",  # not part of ApplicationCreate, must be ignored
        "reference_id": "ONB-HACKED",  # not part of ApplicationCreate, must be ignored
    }
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 422
    assert "email" in response.json()["errors"]
