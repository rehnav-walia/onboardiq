"""Test bootstrap.

The environment variables below MUST be set before anything under `app.*`
is imported for the first time in the test session — `app.config.Settings`
is read once (and cached) at import time, and `app.database` builds its
SQLAlchemy engine from it immediately. Setting env vars afterwards would be
too late.
"""

import os
from pathlib import Path

import pytest

_TEST_DATA_DIR = Path(__file__).parent / "_tmp_test_data"
_STORAGE_DIR = _TEST_DATA_DIR / "storage"
_DB_PATH = _TEST_DATA_DIR / "test.db"
_CHROMA_DIR = _TEST_DATA_DIR / "chroma"

_TEST_DATA_DIR.mkdir(exist_ok=True)
_STORAGE_DIR.mkdir(exist_ok=True)
if _DB_PATH.exists():
    _DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["STORAGE_ROOT"] = str(_STORAGE_DIR)
os.environ["ALLOWED_ORIGINS"] = "http://localhost:5173"
os.environ["MAX_UPLOAD_SIZE_MB"] = "1"
os.environ["REFERENCE_ID_PREFIX"] = "ONB"
# No API key by default — extraction tests either monkeypatch
# app.pipeline.run_extraction directly (bypassing this entirely) or exercise
# the real graceful-degradation-on-missing-key path deliberately.
os.environ["ANTHROPIC_API_KEY"] = ""
# Isolated from dev's ./data/chroma — POLICY_DOCUMENTS_DIR is deliberately
# NOT overridden, so RAG tests ingest and query the *real* shipped sample
# documents (backend/policy_documents/), not synthetic test-only content.
os.environ["CHROMA_PERSIST_DIR"] = str(_CHROMA_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.rag.ingest_cli import run_ingestion  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _ingest_real_policy_documents():
    # Real ingestion against the real shipped sample documents, once per
    # test session — RAG retrieval tests exercise this genuinely, not
    # mocked (only the final answer-synthesis LLM call is ever mocked).
    run_ingestion()


# Reviewer auth (additive, out-of-PRD-scope — see app/auth.py) is
# deliberately NOT mocked here: `reviewer_accounts_file` is left at its
# default, so tests log in against the same real `reviewer_accounts.json`
# shipped with the app, same principle as the RAG tests using the real
# shipped policy documents rather than a synthetic fixture.
DEMO_REVIEWER_USERNAME = "reviewer_1"
DEMO_REVIEWER_PASSWORD = "changeme123"


def reviewer_token(username: str = DEMO_REVIEWER_USERNAME, password: str = DEMO_REVIEWER_PASSWORD) -> str:
    anon = TestClient(app)
    response = anon.post("/api/auth/reviewer/login", json={"username": username, "password": password})
    response.raise_for_status()
    return response.json()["token"]


def reviewer_client(username: str = DEMO_REVIEWER_USERNAME, password: str = DEMO_REVIEWER_PASSWORD) -> TestClient:
    """A TestClient authenticated as a specific demo reviewer — for the rare
    test that needs to prove two distinct reviewers acted (e.g. the
    resubmission loop). Most tests don't need this; the plain `client`
    fixture is already authenticated as DEMO_REVIEWER_USERNAME."""
    return TestClient(app, headers={"Authorization": f"Bearer {reviewer_token(username, password)}"})


@pytest.fixture()
def client() -> TestClient:
    # Authenticated by default as the standard demo reviewer — every
    # existing test that calls a reviewer-only endpoint (queue, decisions)
    # keeps working unchanged, since it was already exercising that
    # identity's behavior implicitly (see docs/PROGRESS.md's reviewer-auth
    # addition for why this is the chosen default).
    return reviewer_client()


@pytest.fixture()
def unauthenticated_client() -> TestClient:
    """A plain, logged-out TestClient — for tests that specifically verify
    reviewer-only endpoints reject requests with no valid session."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Rate limiting (additive, out-of-PRD-scope — see app/rate_limit.py)
    uses process-wide, module-level limiter instances by design (a single
    in-memory limiter shared across the whole app, not per-request state).
    Without resetting them between tests, the application-submission
    limiter (10/hour) would trip partway through this test session purely
    from unrelated tests each submitting one application — this fixture
    is what keeps every test's rate-limit state independent of the others,
    the same way a fresh DB row set or a fresh TestClient would be."""
    from app.rate_limit import application_limiter, login_limiter

    login_limiter.clear_all()
    application_limiter.clear_all()
    yield


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


VALID_APPLICATION_PAYLOAD = {
    "full_name": "Jane Doe",
    "date_of_birth": "1990-05-15",
    "id_number": "A1234567",
    "address": "221B Baker Street, London",
    "email": "jane.doe@example.com",
    "phone": "+1 555 123 4567",
    "account_type": "SAVINGS",
}
