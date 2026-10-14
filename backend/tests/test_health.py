from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.main import app

client = TestClient(app)


def test_api_engine_hides_sql_parameters():
    """Bound values (e.g. password hashes) must never appear in SQL logs or error messages."""
    assert engine.hide_parameters is True
    assert SessionLocal.kw["bind"] is engine  # the sessions the API uses come from this engine


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_connects_to_postgres(client):
    """Uses the rolled-back test-database connection (the `client` fixture), never DB_NAME."""
    response = client.get("/health/db")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == get_settings().test_db_name
