"""Behaviour shared by every list endpoint, plus error-handling details."""

import pytest
from sqlalchemy import text

from tests.api_helpers import company_payload, create


@pytest.fixture
def five_companies(client):
    return [create(client, "/api/companies", company_payload(name=f"Paged {i}")) for i in range(5)]


def test_pagination_limit_offset_and_total_header(client, five_companies):
    full = [c["id"] for c in client.get("/api/companies").json()]
    assert set(full) == {c["id"] for c in five_companies}

    first = client.get("/api/companies", params={"limit": 2})
    second = client.get("/api/companies", params={"limit": 2, "offset": 2})
    last = client.get("/api/companies", params={"limit": 2, "offset": 4})

    assert first.headers["x-total-count"] == "5"
    # Pages are consecutive slices of the same stable order (ties broken by id): no gaps or repeats.
    assert [c["id"] for c in first.json() + second.json() + last.json()] == full
    assert len(last.json()) == 1


def test_total_header_respects_filters(client, five_companies):
    response = client.get("/api/companies", params={"search": "Paged 3", "limit": 1})
    assert response.headers["x-total-count"] == "1"


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}, {"limit": "many"}])
@pytest.mark.parametrize("path", ["/api/companies", "/api/contacts", "/api/deals", "/api/activities"])
def test_invalid_pagination_returns_422(client, path, params):
    assert client.get(path, params=params).status_code == 422


@pytest.mark.parametrize("path", ["/api/companies", "/api/contacts", "/api/deals", "/api/activities"])
def test_empty_lists(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["x-total-count"] == "0"


def test_cors_exposes_total_header(client):
    response = client.get("/api/companies", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-total-count" in response.headers["access-control-expose-headers"].lower()


def test_failed_write_leaves_no_partial_data(client, connection):
    """A 409 rolls back the request's transaction; earlier data is still intact and usable."""
    create(client, "/api/companies", company_payload(name="Only Once"))
    assert client.post("/api/companies", json=company_payload(name="ONLY ONCE")).status_code == 409
    count = connection.execute(text("SELECT count(*) FROM companies WHERE lower(name) = 'only once'")).scalar_one()
    assert count == 1
    # The connection is still healthy after the error.
    create(client, "/api/companies", company_payload(name="After Error"))


def test_invalid_json_body_returns_422(client):
    response = client.post(
        "/api/companies", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
