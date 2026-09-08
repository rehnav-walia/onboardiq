import io

from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


def _upload(client, reference_id, filename="id.jpg", header=JPEG_HEADER, content_type="image/jpeg", declared_type=None):
    data = {}
    if declared_type is not None:
        data["declared_type"] = declared_type
    return client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": (filename, io.BytesIO(header), content_type)},
        data=data,
    )


def test_first_upload_is_version_one_and_not_superseded(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    response = _upload(client, reference_id)
    body = response.json()
    assert body["version"] == 1
    assert body["superseded"] is False


def test_replace_while_info_requested_creates_version_two_and_retains_version_one(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)  # -> AI_UNAVAILABLE -> PENDING_REVIEW (no API key in tests)
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "REQUEST_INFO", "reasoning": "Blurry photo, please retake."},
    )
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "INFO_REQUESTED"

    replace_response = _upload(client, reference_id, filename="id_v2.jpg")
    assert replace_response.status_code == 201
    replaced = replace_response.json()
    assert replaced["version"] == 2
    assert replaced["superseded"] is False

    documents = client.get(f"/api/applications/{reference_id}/documents").json()
    assert len(documents) == 2
    assert documents[0]["version"] == 1
    assert documents[0]["superseded"] is True
    assert documents[1]["version"] == 2
    assert documents[1]["superseded"] is False

    # US-07 DoD: the previous version's file is retained, not deleted —
    # still fetchable.
    old_file_response = client.get(f"/api/applications/{reference_id}/documents/{documents[0]['id']}/file")
    assert old_file_response.status_code == 200


def test_replace_re_triggers_extraction_and_returns_to_pending_review(client):
    """US-25: resubmission after INFO_REQUESTED re-runs the pipeline and
    lands back in PENDING_REVIEW."""
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "REQUEST_INFO", "reasoning": "Please upload a clearer copy."},
    )
    _upload(client, reference_id, filename="id_v2.jpg")

    application = client.get(f"/api/applications/{reference_id}").json()
    assert application["status"] == "PENDING_REVIEW"

    # A second, later decision can now be recorded for this new review cycle.
    approve = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_2", "action": "APPROVE"},
    )
    assert approve.status_code == 201
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "APPROVED"


def test_resubmission_verification_results_do_not_duplicate_across_rounds(client, monkeypatch):
    from app.llm.schemas import LLMExtractionResponse, LLMFieldResult

    def _field(value):
        return LLMFieldResult(value=value, confidence=0.9, justification="Clearly legible.")

    def _fake_response(*args, **kwargs):
        return LLMExtractionResponse(
            readable=True,
            overall_justification="Good quality.",
            full_name=_field(VALID_APPLICATION_PAYLOAD["full_name"]),
            date_of_birth=_field(VALID_APPLICATION_PAYLOAD["date_of_birth"]),
            id_number=_field(VALID_APPLICATION_PAYLOAD["id_number"]),
            document_type=_field("PASSPORT"),
            expiry_date=_field(None),
        )

    monkeypatch.setattr("app.pipeline.run_extraction", _fake_response)

    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "REQUEST_INFO", "reasoning": "Please upload a clearer copy."},
    )
    _upload(client, reference_id, filename="id_v2.jpg")

    extraction = client.get(f"/api/applications/{reference_id}/extraction").json()
    field_names = [v["field_name"] for v in extraction["verification"]]
    # Exactly one row per comparable field (full_name, date_of_birth,
    # id_number) — not one per field per round.
    assert sorted(field_names) == ["date_of_birth", "full_name", "id_number"]


def test_replace_blocked_once_pending_review(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    assert client.get(f"/api/applications/{reference_id}").json()["status"] == "PENDING_REVIEW"

    response = _upload(client, reference_id, filename="id_v2.jpg")
    assert response.status_code == 409


def test_replace_blocked_after_decision(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    _upload(client, reference_id)
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "APPROVE"},
    )

    response = _upload(client, reference_id, filename="id_v2.jpg")
    assert response.status_code == 409


def test_first_upload_allowed_while_draft(client):
    """Uploading before final submission (e.g. an applicant who saves a
    draft partway through) must not be blocked."""
    reference_id = client.post("/api/applications/draft", json={"full_name": "Jane Doe"}).json()["reference_id"]
    response = _upload(client, reference_id)
    assert response.status_code == 201
