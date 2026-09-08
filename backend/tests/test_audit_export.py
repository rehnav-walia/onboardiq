import csv
import io
import json

from tests.conftest import VALID_APPLICATION_PAYLOAD

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def _submit_and_decide(client, reasoning="ID number does not match, contains a comma, and \"quotes\".\nSecond line."):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    client.post(
        f"/api/applications/{reference_id}/documents",
        files={"file": ("id.jpg", io.BytesIO(JPEG_HEADER), "image/jpeg")},
    )
    client.post(
        f"/api/applications/{reference_id}/decision",
        json={"reviewer_id": "reviewer_1", "action": "REJECT", "reasoning": reasoning},
    )
    return reference_id


def test_export_json_includes_audit_entries_and_decision(client):
    reference_id = _submit_and_decide(client, reasoning="Blurry document.")
    response = client.get(f"/api/applications/{reference_id}/audit-log/export?format=json")
    assert response.status_code == 200
    body = response.json()
    assert body["reference_id"] == reference_id
    assert body["final_status"] == "REJECTED"

    record_types = {e["record_type"] for e in body["entries"]}
    assert record_types == {"AUDIT", "DECISION"}

    decision_rows = [e for e in body["entries"] if e["record_type"] == "DECISION"]
    assert len(decision_rows) == 1
    assert decision_rows[0]["actor"] == "reviewer_1"
    assert decision_rows[0]["action"] == "REJECT"
    assert decision_rows[0]["details"] == "Blurry document."

    timestamps = [e["timestamp"] for e in body["entries"]]
    assert timestamps == sorted(timestamps)


def test_export_csv_opens_correctly_and_handles_commas_quotes_and_newlines(client):
    tricky_reasoning = 'ID number does not match, contains a comma, and "quotes".\nSecond line.'
    reference_id = _submit_and_decide(client, reasoning=tricky_reasoning)
    response = client.get(f"/api/applications/{reference_id}/audit-log/export?format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert reference_id in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["record_type", "timestamp", "actor", "action", "details"]

    decision_rows = [r for r in rows[1:] if r[0] == "DECISION"]
    assert len(decision_rows) == 1
    # csv correctly round-trips the embedded comma, quotes, and newline as a
    # single field rather than corrupting the row structure (US-28 DoD).
    assert decision_rows[0][4] == tricky_reasoning
    assert decision_rows[0][2] == "reviewer_1"
    assert decision_rows[0][3] == "REJECT"


def test_export_defaults_to_csv(client):
    reference_id = _submit_and_decide(client)
    response = client.get(f"/api/applications/{reference_id}/audit-log/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_export_does_not_alter_application_state(client):
    """US-28 DoD/AC: export is read-only."""
    reference_id = _submit_and_decide(client)
    before = client.get(f"/api/applications/{reference_id}").json()
    client.get(f"/api/applications/{reference_id}/audit-log/export?format=json")
    client.get(f"/api/applications/{reference_id}/audit-log/export?format=csv")
    after = client.get(f"/api/applications/{reference_id}").json()
    assert before == after
    audit_log = client.get(f"/api/applications/{reference_id}/audit-log").json()
    assert all(not e["action"].startswith("EXPORT") for e in audit_log)


def test_export_rejects_unknown_format(client):
    reference_id = _submit_and_decide(client)
    response = client.get(f"/api/applications/{reference_id}/audit-log/export?format=xml")
    assert response.status_code == 422


def test_export_for_unknown_application_returns_404(client):
    response = client.get("/api/applications/ONB-2026-99999/audit-log/export")
    assert response.status_code == 404


def test_export_before_any_decision_still_includes_audit_entries(client):
    reference_id = client.post("/api/applications", json=VALID_APPLICATION_PAYLOAD).json()["reference_id"]
    response = client.get(f"/api/applications/{reference_id}/audit-log/export?format=json")
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) >= 1
    assert all(e["record_type"] == "AUDIT" for e in body["entries"])
