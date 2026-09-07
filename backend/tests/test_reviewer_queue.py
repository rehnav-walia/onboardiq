from datetime import date

from app import crud
from app.models import AccountType, Application, ApplicationStatus
from app.schemas import ApplicationCreate


def _seed_application(db, index: int, status: ApplicationStatus) -> Application:
    payload = ApplicationCreate(
        full_name=f"Queue Test Applicant {index}",
        date_of_birth=date(1990, 1, 1),
        id_number=f"QID{index:06d}",
        address="1 Test Street",
        email=f"queuetest{index}@example.com",
        phone="+1 555 000 0000",
        account_type=AccountType.SAVINGS,
    )
    application = crud.create_application(db, payload)
    application.status = status
    db.commit()
    db.refresh(application)
    return application


def test_queue_returns_only_pending_review_and_info_requested(client, db_session):
    submitted = _seed_application(db_session, 9001, ApplicationStatus.SUBMITTED)
    pending = _seed_application(db_session, 9002, ApplicationStatus.PENDING_REVIEW)
    info_requested = _seed_application(db_session, 9003, ApplicationStatus.INFO_REQUESTED)
    approved = _seed_application(db_session, 9004, ApplicationStatus.APPROVED)
    rejected = _seed_application(db_session, 9005, ApplicationStatus.REJECTED)

    response = client.get("/api/reviewer/queue?limit=100&offset=0")
    assert response.status_code == 200
    reference_ids = {item["reference_id"] for item in response.json()["items"]}

    assert pending.reference_id in reference_ids
    assert info_requested.reference_id in reference_ids
    assert submitted.reference_id not in reference_ids
    assert approved.reference_id not in reference_ids
    assert rejected.reference_id not in reference_ids


def test_queue_item_fields(client, db_session):
    application = _seed_application(db_session, 9010, ApplicationStatus.PENDING_REVIEW)
    response = client.get("/api/reviewer/queue?limit=100&offset=0")
    item = next(i for i in response.json()["items"] if i["reference_id"] == application.reference_id)
    assert item["full_name"] == "Queue Test Applicant 9010"
    assert item["status"] == "PENDING_REVIEW"
    assert "flag_count" in item
    assert "submitted_at" in item


def test_queue_pagination_with_50_seeded_applications(client, db_session):
    """US-19 DoD: seeded dataset of at least 50 applications."""
    for i in range(50):
        _seed_application(db_session, 9100 + i, ApplicationStatus.PENDING_REVIEW)

    first_page = client.get("/api/reviewer/queue?limit=20&offset=0").json()
    assert first_page["total"] >= 50
    assert len(first_page["items"]) == 20

    second_page = client.get("/api/reviewer/queue?limit=20&offset=20").json()
    assert len(second_page["items"]) == 20

    first_refs = {item["reference_id"] for item in first_page["items"]}
    second_refs = {item["reference_id"] for item in second_page["items"]}
    assert first_refs.isdisjoint(second_refs)


def test_queue_rejects_invalid_limit(client):
    assert client.get("/api/reviewer/queue?limit=0").status_code == 400
    assert client.get("/api/reviewer/queue?limit=1000").status_code == 400


def test_queue_rejects_negative_offset(client):
    assert client.get("/api/reviewer/queue?offset=-1").status_code == 400


def test_queue_empty_page_returns_empty_list_not_error(client):
    response = client.get("/api/reviewer/queue?limit=20&offset=999999")
    assert response.status_code == 200
    assert response.json()["items"] == []
