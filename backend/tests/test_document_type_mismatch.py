import io

from app.verification import compare_document_type
from app.models import DocumentType
from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _fake_extraction_response(detected_document_type):
    from app.llm.schemas import LLMExtractionResponse, LLMFieldResult

    def _field(value):
        return LLMFieldResult(value=value, confidence=0.9, justification="Clearly legible.")

    def _fake(*args, declared_document_type=None, **kwargs):
        return LLMExtractionResponse(
            readable=True,
            overall_justification="Good quality.",
            full_name=_field(VALID_APPLICATION_PAYLOAD["full_name"]),
            date_of_birth=_field(VALID_APPLICATION_PAYLOAD["date_of_birth"]),
            id_number=_field(VALID_APPLICATION_PAYLOAD["id_number"]),
            document_type=_field(detected_document_type),
            expiry_date=_field(None),
        )

    return _fake


# --- Unit tests for the pure comparator -----------------------------------


def test_compare_document_type_matches_case_and_spacing_insensitively():
    assert compare_document_type(DocumentType.PASSPORT, "passport") is False
    assert compare_document_type(DocumentType.NATIONAL_ID, "  national_id  ") is False


def test_compare_document_type_flags_genuine_mismatch():
    assert compare_document_type(DocumentType.PASSPORT, "DRIVING_LICENCE") is True


def test_compare_document_type_flags_other_as_mismatch():
    assert compare_document_type(DocumentType.PASSPORT, "OTHER") is True


def test_compare_document_type_is_none_when_not_declared():
    assert compare_document_type(None, "PASSPORT") is None


def test_compare_document_type_is_none_when_not_detected():
    assert compare_document_type(DocumentType.PASSPORT, None) is None
    assert compare_document_type(DocumentType.PASSPORT, "") is None


# --- End-to-end through the upload + pipeline ------------------------------


def test_declared_type_is_stored_on_upload(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
        data={"declared_type": "PASSPORT"},
    )
    assert response.status_code == 201
    assert response.json()["declared_type"] == "PASSPORT"
    assert response.json()["type_mismatch"] is None  # no API key -> AI_UNAVAILABLE, nothing detected yet


def test_matching_declared_and_detected_type_is_not_flagged(client, monkeypatch):
    monkeypatch.setattr("app.pipeline.run_extraction", _fake_extraction_response("PASSPORT"))
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
        data={"declared_type": "PASSPORT"},
    )
    documents = client.get(f"/api/applications/{reference_id}/documents").json()
    assert documents[0]["detected_type"] == "PASSPORT"
    assert documents[0]["type_mismatch"] is False


def test_mismatched_declared_and_detected_type_is_flagged_and_visible_on_risk(client, monkeypatch):
    """US-15 AC: mismatch raises a flag visible in the review screen (here,
    the risk assessment's contributing factors) and does not auto-reject."""
    monkeypatch.setattr("app.pipeline.run_extraction", _fake_extraction_response("DRIVING_LICENCE"))
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
        data={"declared_type": "PASSPORT"},
    )
    documents = client.get(f"/api/applications/{reference_id}/documents").json()
    assert documents[0]["type_mismatch"] is True

    risk = client.get(f"/api/applications/{reference_id}/risk").json()
    codes = [f["code"] for f in risk["factors"]]
    assert "DECLARED_TYPE_MISMATCH" in codes

    application = client.get(f"/api/applications/{reference_id}").json()
    # Does not auto-reject — still sitting in the ordinary review queue status.
    assert application["status"] == "PENDING_REVIEW"


def test_declared_type_is_passed_to_extraction_as_context(client, monkeypatch):
    captured = {}

    def _capture(file_bytes, media_type, declared_document_type):
        captured["declared_document_type"] = declared_document_type
        from app.llm.errors import AIUnavailableError

        raise AIUnavailableError("stub")

    monkeypatch.setattr("app.pipeline.run_extraction", _capture)
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
        data={"declared_type": "NATIONAL_ID"},
    )
    assert captured["declared_document_type"] == "NATIONAL_ID"


def test_declared_type_rejects_values_outside_the_controlled_list(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
        data={"declared_type": "SOMETHING_ELSE"},
    )
    assert response.status_code == 422
