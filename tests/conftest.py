import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "CentralServer"))
sys.path.insert(0, str(ROOT / "AgentManager" / "src"))

database_fd, database_path = tempfile.mkstemp(prefix="virtualmanager-tests-", suffix=".sqlite3")
os.close(database_fd)
os.environ["VIRTUALMANAGER_DATABASE_URL"] = f"sqlite:///{Path(database_path).as_posix()}"
os.environ["VIRTUALMANAGER_ENROLLMENT_TOKEN"] = "test-enrollment-token"
os.environ["VIRTUALMANAGER_WEB_USERNAME"] = "admin"
os.environ["VIRTUALMANAGER_WEB_PASSWORD"] = "TestPassword123!"

from src import main, models  # noqa: E402
from src.database import SessionLocal  # noqa: E402
from src.migrations import upgrade_database  # noqa: E402
from tests.helpers import TEST_PASSWORD  # noqa: E402


TEST_PASSWORD_HASH = main.hash_password(TEST_PASSWORD)


@pytest.fixture(autouse=True)
def clean_database():
    upgrade_database()
    with main.engine.begin() as connection:
        for table in reversed(main.Base.metadata.sorted_tables):
            connection.execute(table.delete())
    with SessionLocal() as database:
        database.add(models.WebUser(
            id="00000000-0000-0000-0000-000000000001",
            username="admin",
            password_hash=TEST_PASSWORD_HASH,
            role="admin",
            is_active=True,
        ))
        database.commit()
    yield


@pytest.fixture
def client():
    with TestClient(main.app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def admin_client(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert response.status_code == 200
    return client


def pytest_sessionfinish(session, exitstatus):
    main.engine.dispose()
    Path(database_path).unlink(missing_ok=True)
