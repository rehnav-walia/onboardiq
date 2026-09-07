from datetime import date, datetime, timedelta, timezone

from app import crud
from app.models import AccountType, Application, ApplicationStatus, RiskLevel
from app.schemas import ApplicationCreate


def _seed_application(
    db,
    index: int,
    status: ApplicationStatus,
    risk_level: RiskLevel | None = None,
    pending_review_since: datetime | None = None,
) -> Application:
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
    application.risk_level = risk_level
    application.pending_review_since = pending_review_since
    db.commit()
    db.refresh(application)
    return application


def test_queue_returns_only_pending_review_and_info_requested(client, db_session):
    submitted = _seed_application(db_session, 9001, ApplicationStatus.SUBMITTED)
    pending = _seed_application(db_session, 9002, ApplicationStatus.PENDING_REVIEW)
    info_requested = _seed_application(db_session, 9003, ApplicationStatus.INFO_REQUESTED)
    approved = _seed_application(db_session, 9004, ApplicationStatus.APPROVED)
    rejected = _seed_application(db_session, 9005, ApplicationStatus.REJECTED)

    response = client.get("/api/reviewer/queue?limit=100&offset=0&sort_dir=desc")
    assert response.status_code == 200
    reference_ids = {item["reference_id"] for item in response.json()["items"]}

    assert pending.reference_id in reference_ids
    assert info_requested.reference_id in reference_ids
    assert submitted.reference_id not in reference_ids
    assert approved.reference_id not in reference_ids
    assert rejected.reference_id not in reference_ids


def test_queue_item_fields(client, db_session):
    application = _seed_application(db_session, 9010, ApplicationStatus.PENDING_REVIEW)
    response = client.get("/api/reviewer/queue?limit=100&offset=0&sort_dir=desc")
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


# --- Sorting and filtering (US-20) -----------------------------------------


def test_queue_filter_by_status(client, db_session):
    pending = _seed_application(db_session, 9200, ApplicationStatus.PENDING_REVIEW)
    info_requested = _seed_application(db_session, 9201, ApplicationStatus.INFO_REQUESTED)

    response = client.get("/api/reviewer/queue?status=INFO_REQUESTED&limit=100&sort_dir=desc")
    reference_ids = {item["reference_id"] for item in response.json()["items"]}
    assert info_requested.reference_id in reference_ids
    assert pending.reference_id not in reference_ids


def test_queue_rejects_non_queue_status(client):
    response = client.get("/api/reviewer/queue?status=APPROVED")
    assert response.status_code == 400


def test_queue_filter_by_risk_level(client, db_session):
    high = _seed_application(db_session, 9210, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.HIGH)
    low = _seed_application(db_session, 9211, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.LOW)

    response = client.get("/api/reviewer/queue?risk_level=HIGH&limit=100&sort_dir=desc")
    reference_ids = {item["reference_id"] for item in response.json()["items"]}
    assert high.reference_id in reference_ids
    assert low.reference_id not in reference_ids


def test_queue_sort_by_risk_level_descending_puts_high_first(client, db_session):
    low = _seed_application(db_session, 9220, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.LOW)
    high = _seed_application(db_session, 9221, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.HIGH)
    medium = _seed_application(db_session, 9222, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.MEDIUM)

    response = client.get("/api/reviewer/queue?sort_by=risk_level&sort_dir=desc&limit=100").json()
    ordered_refs = [item["reference_id"] for item in response["items"]]
    seeded_in_order = [r for r in ordered_refs if r in {low.reference_id, high.reference_id, medium.reference_id}]
    assert seeded_in_order == [high.reference_id, medium.reference_id, low.reference_id]


def test_queue_sort_by_submission_time_ascending_is_still_the_default(db_session):
    """Exercises crud.list_queue directly (not the HTTP-capped page size) so
    this stays valid regardless of how many rows earlier tests in this
    session have accumulated."""
    first = _seed_application(db_session, 9230, ApplicationStatus.PENDING_REVIEW)
    second = _seed_application(db_session, 9231, ApplicationStatus.PENDING_REVIEW)

    _, items = crud.list_queue(db_session, limit=100000, offset=0)
    ordered_refs = [item.reference_id for item in items]
    assert ordered_refs.index(first.reference_id) < ordered_refs.index(second.reference_id)


def test_queue_rejects_invalid_sort_by(client):
    assert client.get("/api/reviewer/queue?sort_by=full_name").status_code == 400


def test_queue_rejects_invalid_sort_dir(client):
    assert client.get("/api/reviewer/queue?sort_dir=sideways").status_code == 400


def test_queue_combined_filter_and_sort(client, db_session):
    """US-20 DoD: combined filter and sort verified together."""
    _seed_application(db_session, 9240, ApplicationStatus.INFO_REQUESTED, risk_level=RiskLevel.LOW)
    target_high = _seed_application(db_session, 9241, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.HIGH)
    target_medium = _seed_application(
        db_session, 9242, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.MEDIUM
    )
    _seed_application(db_session, 9243, ApplicationStatus.PENDING_REVIEW, risk_level=RiskLevel.LOW)

    response = client.get(
        "/api/reviewer/queue?status=PENDING_REVIEW&sort_by=risk_level&sort_dir=desc&limit=100"
    ).json()
    ordered_refs = [item["reference_id"] for item in response["items"]]
    relevant = [r for r in ordered_refs if r in {target_high.reference_id, target_medium.reference_id}]
    assert relevant == [target_high.reference_id, target_medium.reference_id]


# --- Ageing / overdue (US-21) ------------------------------------------------


def test_queue_shows_hours_waiting_and_marks_overdue_past_threshold(client, db_session):
    """US-21 DoD: timezone handling verified — pending_review_since is
    stored as aware UTC; this asserts the elapsed-time math is actually
    correct against a known, deliberately-old timestamp, not just present."""
    overdue_since = datetime.now(timezone.utc) - timedelta(hours=48)
    overdue_app = _seed_application(
        db_session, 9250, ApplicationStatus.PENDING_REVIEW, pending_review_since=overdue_since
    )
    fresh_app = _seed_application(
        db_session,
        9251,
        ApplicationStatus.PENDING_REVIEW,
        pending_review_since=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    response = client.get("/api/reviewer/queue?limit=100&sort_dir=desc").json()
    items_by_ref = {item["reference_id"]: item for item in response["items"]}

    overdue_item = items_by_ref[overdue_app.reference_id]
    assert overdue_item["is_overdue"] is True
    assert overdue_item["hours_waiting"] > 24  # default OVERDUE_THRESHOLD_HOURS

    fresh_item = items_by_ref[fresh_app.reference_id]
    assert fresh_item["is_overdue"] is False
    assert fresh_item["hours_waiting"] < 24


def test_queue_overdue_only_filter(client, db_session):
    overdue_app = _seed_application(
        db_session,
        9260,
        ApplicationStatus.PENDING_REVIEW,
        pending_review_since=datetime.now(timezone.utc) - timedelta(hours=48),
    )
    fresh_app = _seed_application(
        db_session,
        9261,
        ApplicationStatus.PENDING_REVIEW,
        pending_review_since=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    response = client.get("/api/reviewer/queue?overdue_only=true&limit=100").json()
    reference_ids = {item["reference_id"] for item in response["items"]}
    assert overdue_app.reference_id in reference_ids
    assert fresh_app.reference_id not in reference_ids


def test_queue_item_without_pending_review_since_is_not_overdue(client, db_session):
    """Applications seeded without a timestamp (or, in the real pipeline,
    that haven't reached PENDING_REVIEW through it) must not crash the
    ageing computation or be misreported as overdue."""
    application = _seed_application(db_session, 9270, ApplicationStatus.PENDING_REVIEW)
    # Newest-first with the max page size: robust against however many
    # PENDING_REVIEW rows earlier tests in this session have accumulated
    # (limit is capped at 100 — a plain limit=100 in submission order could
    # push this just-created row off the page).
    response = client.get("/api/reviewer/queue?limit=100&sort_dir=desc").json()
    item = next(i for i in response["items"] if i["reference_id"] == application.reference_id)
    assert item["is_overdue"] is False
    assert item["hours_waiting"] is None
