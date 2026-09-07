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


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


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
