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

_TEST_DATA_DIR.mkdir(exist_ok=True)
_STORAGE_DIR.mkdir(exist_ok=True)
if _DB_PATH.exists():
    _DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["STORAGE_ROOT"] = str(_STORAGE_DIR)
os.environ["ALLOWED_ORIGINS"] = "http://localhost:5173"
os.environ["MAX_UPLOAD_SIZE_MB"] = "1"
os.environ["REFERENCE_ID_PREFIX"] = "ONB"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


VALID_APPLICATION_PAYLOAD = {
    "full_name": "Jane Doe",
    "date_of_birth": "1990-05-15",
    "id_number": "A1234567",
    "address": "221B Baker Street, London",
    "email": "jane.doe@example.com",
    "phone": "+1 555 123 4567",
    "account_type": "SAVINGS",
}
