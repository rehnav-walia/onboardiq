from datetime import date, datetime, timedelta, timezone

from app import crud
from app.models import AccountType, Application, ApplicationStatus
from app.schemas import ApplicationCreate


def _seed_application(
    db,
    index: int,
    status: ApplicationStatus,
    pending_review_since: datetime | None = None,
) -> Application:
    payload = ApplicationCreate(
        full_name=f"Stats Test Applicant {index}",
        date_of_birth=date(1990, 1, 1),
        id_number=f"STQ{index:06d}",
        address="1 Test Street",
        email=f"statstest{index}@example.com",
        phone="+1 555 000 0000",
        account_type=AccountType.SAVINGS,
    )
    application = crud.create_application(db, payload)
    application.status = status
    application.pending_review_since = pending_review_since
    db.commit()
    db.refresh(application)
    return application


def test_queue_stats_requires_reviewer_auth(unauthenticated_client):
    response = unauthenticated_client.get("/api/reviewer/queue/stats")
    assert response.status_code == 401


def test_queue_stats_shape(client):
    response = client.get("/api/reviewer/queue/stats")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"pending_review", "info_requested", "approved", "rejected", "overdue"}
    assert all(isinstance(v, int) for v in body.values())


def test_queue_stats_counts_match_seeded_data(client, db_session):
    """The whole point of this endpoint: each count matches how many
    applications actually sit in that status, including APPROVED/REJECTED,
    which crud.list_queue's own results never include at all. Asserted as a
    delta (not an absolute count) because the test database accumulates
    applications across this whole pytest session — see conftest.py and
    the same pattern in tests/test_reviewer_queue.py."""
    before = client.get("/api/reviewer/queue/stats").json()

    _seed_application(db_session, 9500, ApplicationStatus.PENDING_REVIEW)
    _seed_application(db_session, 9501, ApplicationStatus.PENDING_REVIEW)
    _seed_application(db_session, 9502, ApplicationStatus.INFO_REQUESTED)
    _seed_application(db_session, 9503, ApplicationStatus.APPROVED)
    _seed_application(db_session, 9504, ApplicationStatus.REJECTED)
    _seed_application(db_session, 9505, ApplicationStatus.REJECTED)

    after = client.get("/api/reviewer/queue/stats").json()

    assert after["pending_review"] - before["pending_review"] == 2
    assert after["info_requested"] - before["info_requested"] == 1
    assert after["approved"] - before["approved"] == 1
    assert after["rejected"] - before["rejected"] == 2


def test_queue_stats_excludes_draft_submitted_and_processing(client, db_session):
    """Statuses that never reach the reviewer queue must not inflate any
    bucket here either — this endpoint reports where applications
    currently stand for a reviewer, not every row in the table."""
    before = client.get("/api/reviewer/queue/stats").json()

    _seed_application(db_session, 9510, ApplicationStatus.DRAFT)
    _seed_application(db_session, 9511, ApplicationStatus.SUBMITTED)
    _seed_application(db_session, 9512, ApplicationStatus.PROCESSING)

    after = client.get("/api/reviewer/queue/stats").json()
    assert after == before


def test_queue_stats_overdue_count_matches_queues_own_overdue_filter(client, db_session):
    """Mirrors tests/test_reviewer_queue.py's overdue tests (US-21): the
    same cutoff, the same two statuses eligible for overdue, so this number
    and the queue's own "Overdue only" filter can never disagree."""
    before = client.get("/api/reviewer/queue/stats").json()

    overdue_since = datetime.now(timezone.utc) - timedelta(hours=48)
    fresh_since = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed_application(db_session, 9520, ApplicationStatus.PENDING_REVIEW, pending_review_since=overdue_since)
    _seed_application(db_session, 9521, ApplicationStatus.INFO_REQUESTED, pending_review_since=overdue_since)
    _seed_application(db_session, 9522, ApplicationStatus.PENDING_REVIEW, pending_review_since=fresh_since)
    # Overdue only ever counts PENDING_REVIEW/INFO_REQUESTED — an overdue-
    # looking timestamp on an already-decided application must not count.
    _seed_application(db_session, 9523, ApplicationStatus.APPROVED, pending_review_since=overdue_since)

    after = client.get("/api/reviewer/queue/stats").json()
    assert after["overdue"] - before["overdue"] == 2
