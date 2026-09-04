import io

from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
PDF_HEADER = b"%PDF-1.4\n" + b"\x00" * 20


def _create_application(client) -> str:
    return client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]


def test_upload_jpeg_succeeds_and_returns_preview_url(client):
    reference_id = _create_application(client)
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id_front.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "id_front.jpg"
    assert body["content_type"] == "image/jpeg"
    assert body["preview_url"].endswith(f"/api/applications/{reference_id}/documents/{body['id']}/file")


def test_upload_png_succeeds(client):
    reference_id = _create_application(client)
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.png", io.BytesIO(PNG_HEADER), "image/png")},
    )
    assert response.status_code == 201
    assert response.json()["content_type"] == "image/png"


def test_upload_pdf_succeeds(client):
    reference_id = _create_application(client)
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.pdf", io.BytesIO(PDF_HEADER), "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["content_type"] == "application/pdf"


def test_content_sniffing_rejects_mislabelled_file(client):
    """US-05 DoD: validated by content, not by extension — a plain text
    file renamed to .png must still be rejected."""
    reference_id = _create_application(client)
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("fake.png", io.BytesIO(b"just plain text, not a real png"), "image/png")},
    )
    assert response.status_code == 400
    assert "unsupported" in response.json()["message"].lower()


def test_oversized_upload_rejected_with_clear_message(client):
    # conftest sets MAX_UPLOAD_SIZE_MB=1 for the test session.
    reference_id = _create_application(client)
    oversized = JPEG_HEADER + b"\x00" * (1 * 1024 * 1024)
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("big.jpg", io.BytesIO(oversized), "image/jpeg")},
    )
    assert response.status_code == 413
    assert "mb limit" in response.json()["message"].lower()


def test_upload_to_unknown_application_returns_404(client):
    """US-05 DoD: an upload can never be linked to a nonexistent application —
    there is no orphan path because there is nothing to attach it to."""
    response = client.post(
        "/api/applications/ONB-2026-99999/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    assert response.status_code == 404


def test_preview_is_served_inline_not_as_attachment(client):
    reference_id = _create_application(client)
    upload = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    ).json()

    response = client.get(f"/api/applications/{reference_id}/documents/{upload['id']}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "inline" in response.headers["content-disposition"]
    assert "attachment" not in response.headers["content-disposition"]


def test_document_storage_path_is_not_derived_from_client_filename(client):
    """US-05 DoD: a path-traversal attempt in the filename must not affect
    where — or whether — the file is stored, and is never echoed back as a
    filesystem path."""
    reference_id = _create_application(client)
    response = client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("../../evil.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert "file_path" not in body
    assert body["original_filename"] in ("evil.jpg", "../../evil.jpg")
