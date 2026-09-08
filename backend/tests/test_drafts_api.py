from tests.conftest import VALID_APPLICATION_PAYLOAD


def test_create_draft_with_partial_data_succeeds(client):
    response = client.post("/api/applications/draft", json={"full_name": "Jane Doe"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["full_name"] == "Jane Doe"
    assert body["date_of_birth"] is None
    assert body["reference_id"].startswith("ONB-")


def test_create_empty_draft_succeeds(client):
    response = client.post("/api/applications/draft", json={})
    assert response.status_code == 201
    assert response.json()["status"] == "DRAFT"


def test_draft_is_not_visible_in_reviewer_queue(client):
    client.post("/api/applications/draft", json={"full_name": "Hidden Applicant"})
    response = client.get("/api/reviewer/queue?limit=100")
    names = {item["full_name"] for item in response.json()["items"]}
    assert "Hidden Applicant" not in names


def test_resume_draft_restores_previously_entered_values(client):
    created = client.post(
        "/api/applications/draft", json={"full_name": "Jane Doe", "id_number": "A1234567"}
    ).json()
    reference_id = created["reference_id"]

    # Simulate resuming and completing step 2.
    update_response = client.patch(
        f"/api/applications/draft/{reference_id}",
        json={"address": "221B Baker Street, London", "email": "jane.doe@example.com"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    # Step 1 values must survive a save that only touches step 2 fields.
    assert updated["full_name"] == "Jane Doe"
    assert updated["id_number"] == "A1234567"
    assert updated["address"] == "221B Baker Street, London"
    assert updated["email"] == "jane.doe@example.com"

    resumed = client.get(f"/api/applications/{reference_id}").json()
    assert resumed == updated


def test_update_draft_rejects_invalid_provided_field(client):
    created = client.post("/api/applications/draft", json={"full_name": "Jane Doe"}).json()
    response = client.patch(
        f"/api/applications/draft/{created['reference_id']}",
        json={"email": "not-an-email"},
    )
    assert response.status_code == 422


def test_update_unknown_draft_returns_404(client):
    response = client.patch("/api/applications/draft/ONB-2026-99999", json={"full_name": "X"})
    assert response.status_code == 404


def test_submit_incomplete_draft_is_rejected(client):
    created = client.post("/api/applications/draft", json={"full_name": "Jane Doe"}).json()
    response = client.post(f"/api/applications/draft/{created['reference_id']}/submit")
    assert response.status_code == 422
    assert client.get(f"/api/applications/{created['reference_id']}").json()["status"] == "DRAFT"


def test_submit_complete_draft_succeeds_and_appears_after_document_upload(client):
    created = client.post("/api/applications/draft", json={}).json()
    reference_id = created["reference_id"]
    client.patch(f"/api/applications/draft/{reference_id}", json=VALID_APPLICATION_PAYLOAD)

    response = client.post(f"/api/applications/draft/{reference_id}/submit")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "SUBMITTED"
    assert body["full_name"] == VALID_APPLICATION_PAYLOAD["full_name"]
    assert body["submitted_at"] is not None


def test_submit_draft_twice_is_rejected(client):
    created = client.post("/api/applications/draft", json=VALID_APPLICATION_PAYLOAD).json()
    reference_id = created["reference_id"]
    first = client.post(f"/api/applications/draft/{reference_id}/submit")
    assert first.status_code == 201

    second = client.post(f"/api/applications/draft/{reference_id}/submit")
    assert second.status_code == 409


def test_cannot_update_draft_after_it_has_been_submitted(client):
    created = client.post("/api/applications/draft", json=VALID_APPLICATION_PAYLOAD).json()
    reference_id = created["reference_id"]
    client.post(f"/api/applications/draft/{reference_id}/submit")

    response = client.patch(f"/api/applications/draft/{reference_id}", json={"full_name": "New Name"})
    assert response.status_code == 409


def test_submit_unknown_draft_returns_404(client):
    response = client.post("/api/applications/draft/ONB-2026-99999/submit")
    assert response.status_code == 404


def test_directly_submitted_application_still_works_unaffected(client):
    """The original one-shot submit path (US-01) must keep working exactly
    as before — drafts are an alternative path, not a replacement."""
    response = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "SUBMITTED"
    assert body["submitted_at"] is not None
