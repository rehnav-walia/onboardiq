import io

from app import crud
from app.llm.errors import AIUnavailableError
from app.llm.schemas import LLMExtractionResponse, LLMFieldResult
from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _field(value, confidence=0.9, justification="Clearly legible."):
    return LLMFieldResult(value=value, confidence=confidence, justification=justification)


def _response(
    readable=True,
    full_name="Jane Doe",
    dob="1990-05-15",
    id_number="A1234567",
    document_type="PASSPORT",
    overall="Document quality is good.",
    full_name_confidence=0.9,
):
    return LLMExtractionResponse(
        readable=readable,
        overall_justification=overall,
        full_name=_field(full_name, confidence=full_name_confidence),
        date_of_birth=_field(dob),
        id_number=_field(id_number),
        document_type=_field(document_type),
    )


def _submit_application(client) -> str:
    return client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]


def _upload(client, reference_id):
    return client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )


def test_upload_never_returns_an_error_even_when_extraction_fails(client, monkeypatch):
    """CLAUDE.md non-negotiable: graceful degradation, never error out to
    the applicant — the upload response must still be a normal 201."""
    monkeypatch.setattr("app.pipeline.run_extraction", lambda *a, **k: (_ for _ in ()).throw(AIUnavailableError("boom")))
    reference_id = _submit_application(client)
    response = _upload(client, reference_id)
    assert response.status_code == 201


def test_successful_extraction_with_matching_data(client, monkeypatch):
    monkeypatch.setattr("app.pipeline.run_extraction", lambda *a, **k: _response())
    reference_id = _submit_application(client)
    _upload(client, reference_id)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["application_status"] == "PENDING_REVIEW"
    assert body["extraction"]["status"] == "SUCCESS"
    assert body["flag_count"] == 0
    statuses = {v["field_name"]: v["match_status"] for v in body["verification"]}
    assert statuses == {"full_name": "MATCH", "date_of_birth": "MATCH", "id_number": "MATCH"}


def test_mismatched_name_is_flagged_and_others_still_compared(client, monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.run_extraction",
        lambda *a, **k: _response(full_name="Someone Else"),
    )
    reference_id = _submit_application(client)
    _upload(client, reference_id)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["flag_count"] == 1
    statuses = {v["field_name"]: v["match_status"] for v in body["verification"]}
    assert statuses["full_name"] == "MISMATCH"
    assert statuses["date_of_birth"] == "MATCH"
    assert statuses["id_number"] == "MATCH"


def test_low_confidence_field_is_flagged_against_configured_threshold(client, monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.run_extraction",
        lambda *a, **k: _response(full_name_confidence=0.2),
    )
    reference_id = _submit_application(client)
    _upload(client, reference_id)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["extraction"]["fields"]["full_name"]["is_low_confidence"] is True
    assert body["extraction"]["fields"]["date_of_birth"]["is_low_confidence"] is False


def test_unreadable_document_persists_no_field_values(client, monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.run_extraction",
        lambda *a, **k: _response(
            readable=False, full_name=None, dob=None, id_number=None, document_type=None, overall="Image is blank."
        ),
    )
    reference_id = _submit_application(client)
    _upload(client, reference_id)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["extraction"]["status"] == "UNREADABLE"
    assert body["extraction"]["fields"] == {}
    assert body["verification"] == []
    assert body["application_status"] == "PENDING_REVIEW"


def test_ai_unavailable_routes_to_review_and_writes_audit_entry(client, db_session, monkeypatch):
    def _boom(*args, **kwargs):
        raise AIUnavailableError("simulated timeout")

    monkeypatch.setattr("app.pipeline.run_extraction", _boom)
    reference_id = _submit_application(client)
    _upload(client, reference_id)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["extraction"]["status"] == "AI_UNAVAILABLE"
    assert body["application_status"] == "PENDING_REVIEW"
    assert body["verification"] == []

    application = crud.get_application_by_reference(db_session, reference_id)
    audit_entries = crud.list_audit_log_entries(db_session, application.id)
    actions = [entry.action for entry in audit_entries]
    assert "EXTRACTION_FAILED" in actions


def test_unexpected_exception_in_pipeline_still_returns_normal_upload_response(client, monkeypatch):
    """Even a genuine bug (not an AIUnavailableError) must not surface as a
    server error to the applicant."""
    monkeypatch.setattr("app.pipeline.run_extraction", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bug")))
    reference_id = _submit_application(client)
    response = _upload(client, reference_id)
    assert response.status_code == 201

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["application_status"] == "PENDING_REVIEW"
    assert body["extraction"]["status"] == "AI_UNAVAILABLE"


def test_extraction_is_idempotent_on_success(client, db_session, monkeypatch):
    """US-09 DoD: re-running does not duplicate results."""
    from app import pipeline

    call_count = {"n": 0}

    def _counting_response(*args, **kwargs):
        call_count["n"] += 1
        return _response()

    monkeypatch.setattr("app.pipeline.run_extraction", _counting_response)
    reference_id = _submit_application(client)
    _upload(client, reference_id)  # first (and only expected) real attempt

    application = crud.get_application_by_reference(db_session, reference_id)
    document = crud.list_documents(db_session, application.id)[-1]

    # Calling the pipeline again directly must be a no-op.
    pipeline.process_document(db_session, application, document)
    pipeline.process_document(db_session, application, document)

    assert call_count["n"] == 1


def test_extraction_retries_after_ai_unavailable(client, db_session, monkeypatch):
    """A failed (AI_UNAVAILABLE) attempt is not treated as final — a
    subsequent run is allowed to actually try again."""
    from app import pipeline

    monkeypatch.setattr(
        "app.pipeline.run_extraction",
        lambda *a, **k: (_ for _ in ()).throw(AIUnavailableError("first attempt fails")),
    )
    reference_id = _submit_application(client)
    _upload(client, reference_id)

    monkeypatch.setattr("app.pipeline.run_extraction", lambda *a, **k: _response())
    application = crud.get_application_by_reference(db_session, reference_id)
    document = crud.list_documents(db_session, application.id)[-1]
    pipeline.process_document(db_session, application, document)

    body = client.get(f"/api/applications/{reference_id}/extraction").json()
    assert body["extraction"]["status"] == "SUCCESS"
