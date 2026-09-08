"""US-24 / CLAUDE.md non-negotiable #1: no code path may set an application
to APPROVED without a recorded human reviewer decision. This must be
provable by an automated test — these are that test.
"""

import inspect
import io
from pathlib import Path

from app import crud, pipeline
from app.models import ApplicationStatus
from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def test_approved_status_is_never_referenced_by_the_ai_pipeline():
    source = inspect.getsource(pipeline)
    assert "ApplicationStatus.APPROVED" not in source


def test_approved_status_is_only_assignable_from_the_decision_flow():
    """Whole-codebase guarantee: the string ApplicationStatus.APPROVED must
    appear in exactly one file outside its own enum definition — crud.py's
    create_decision, which is only reachable through an endpoint that
    requires a validated, non-blank reviewer_id."""
    app_dir = Path(__file__).resolve().parent.parent / "app"
    matches = []
    for path in app_dir.rglob("*.py"):
        if path.name == "models.py":
            continue  # the enum's own definition
        if "ApplicationStatus.APPROVED" in path.read_text(encoding="utf-8"):
            matches.append(str(path.relative_to(app_dir)))
    assert matches == ["crud.py"], (
        "ApplicationStatus.APPROVED must only be assignable from crud.py's "
        f"decision flow; found it referenced in: {matches}"
    )


def test_approve_via_api_without_reviewer_id_fails(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )

    response = client.post(f"/api/applications/{reference_id}/decision", json={"action": "APPROVE"})
    assert response.status_code == 422

    application = client.get(f"/api/applications/{reference_id}").json()
    assert application["status"] != "APPROVED"


def test_approve_via_api_with_blank_reviewer_id_fails(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )

    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "", "action": "APPROVE"},
    )
    assert response.status_code == 422

    application = client.get(f"/api/applications/{reference_id}").json()
    assert application["status"] != "APPROVED"


def test_no_endpoint_allows_setting_status_directly(client):
    """There is no generic "update application" endpoint — status only ever
    changes via the pipeline (which never assigns APPROVED — see above) or
    the decision endpoint (which requires reviewer_id)."""
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    response = client.patch(f"/api/applications/{reference_id}", json={"status": "APPROVED"})
    assert response.status_code in (404, 405)

    application = client.get(f"/api/applications/{reference_id}").json()
    assert application["status"] != "APPROVED"


def test_full_approval_requires_a_recorded_decision(client, db_session):
    """Positive-path proof: the only way to reach APPROVED at all leaves a
    Decision row naming the reviewer — there is no untraceable path to it."""
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    response = client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "APPROVE"},
    )
    assert response.status_code == 201

    application = crud.get_application_by_reference(db_session, reference_id)
    assert application.status == ApplicationStatus.APPROVED

    decision = crud.get_latest_decision(db_session, application.id)
    assert decision is not None
    assert decision.reviewer_id == "reviewer_1"
