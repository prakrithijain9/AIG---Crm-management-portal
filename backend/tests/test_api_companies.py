import uuid

import pytest
from sqlalchemy import text

from tests.api_helpers import (
    activity_payload,
    company_payload,
    contact_payload,
    create,
    deal_payload,
    error_fields,
)

URL = "/api/companies"


def test_create_returns_201_with_camelcase_body(client):
    body = create(client, URL, company_payload(name="Northwind Logistics"))
    assert set(body) == {"id", "name", "industry", "email", "phone", "location", "status", "createdAt", "updatedAt"}
    uuid.UUID(body["id"])
    assert body["name"] == "Northwind Logistics"


def test_create_trims_whitespace_and_defaults_status(client):
    payload = company_payload(name="  Helios Energy  ")
    del payload["status"]
    body = create(client, URL, payload)
    assert body["name"] == "Helios Energy"
    assert body["status"] == "Prospect"


def test_get_by_id(client):
    created = create(client, URL, company_payload())
    response = client.get(f"{URL}/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_missing_returns_404(client):
    response = client.get(f"{URL}/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Company not found"}


def test_malformed_id_returns_422(client):
    assert client.get(f"{URL}/cmp-1").status_code == 422


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"name": "   "}, "name"),
        ({"email": "not-an-email"}, "email"),
        ({"status": "Archived"}, "status"),
        ({"name": "x" * 201}, "name"),
    ],
)
def test_create_validation_errors(client, override, field):
    response = client.post(URL, json=company_payload(**override))
    assert response.status_code == 422
    assert field in error_fields(response)


def test_missing_required_field_returns_422(client):
    payload = company_payload()
    del payload["industry"]
    response = client.post(URL, json=payload)
    assert response.status_code == 422
    assert "industry" in error_fields(response)


def test_unknown_or_snake_case_fields_are_rejected(client):
    response = client.post(URL, json=company_payload(website="x.example"))
    assert response.status_code == 422
    assert "website" in error_fields(response)


def test_duplicate_name_case_insensitive_returns_409(client):
    create(client, URL, company_payload(name="Summit Retail Group"))
    response = client.post(URL, json=company_payload(name="SUMMIT retail group"))
    assert response.status_code == 409
    assert response.json() == {"detail": "A company with this name already exists."}


def test_update_partial(client):
    created = create(client, URL, company_payload(status="Prospect"))
    response = client.patch(f"{URL}/{created['id']}", json={"status": "Active", "location": "Austin, TX"})
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["location"]) == ("Active", "Austin, TX")
    assert body["name"] == created["name"]  # untouched


def test_update_to_duplicate_name_returns_409(client):
    create(client, URL, company_payload(name="Lumen Media"))
    other = create(client, URL, company_payload())
    response = client.patch(f"{URL}/{other['id']}", json={"name": "lumen media"})
    assert response.status_code == 409


def test_update_rejects_null_and_unknown_fields(client):
    created = create(client, URL, company_payload())
    assert client.patch(f"{URL}/{created['id']}", json={"name": None}).status_code == 422
    assert client.patch(f"{URL}/{created['id']}", json={"id": str(uuid.uuid4())}).status_code == 422


def test_update_missing_returns_404(client):
    assert client.patch(f"{URL}/{uuid.uuid4()}", json={"name": "X"}).status_code == 404


def test_delete_then_404(client):
    created = create(client, URL, company_payload())
    response = client.delete(f"{URL}/{created['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"{URL}/{created['id']}").status_code == 404
    assert client.delete(f"{URL}/{created['id']}").status_code == 404


def test_delete_cascades_to_contacts_deals_and_activities(client):
    company = create(client, URL, company_payload())
    contact = create(client, "/api/contacts", contact_payload(company["id"]))
    deal = create(client, "/api/deals", deal_payload(company["id"]))
    activity = create(client, "/api/activities", activity_payload(company["id"], contact["id"]))

    assert client.delete(f"{URL}/{company['id']}").status_code == 204
    assert client.get(f"/api/contacts/{contact['id']}").status_code == 404
    assert client.get(f"/api/deals/{deal['id']}").status_code == 404
    assert client.get(f"/api/activities/{activity['id']}").status_code == 404


def test_list_search_status_filter_and_newest_first(client, connection):
    a = create(client, URL, company_payload(name="Aperture Analytics", industry="Software", status="Prospect"))
    b = create(client, URL, company_payload(name="Vertex Manufacturing", industry="Manufacturing", status="Active"))
    c = create(client, URL, company_payload(name="Harbor & Co.", industry="Financial Services", status="Inactive"))
    # now() is the transaction start time, and all test requests share one transaction,
    # so give the rows distinct creation times explicitly.
    for day, row in enumerate((a, b, c), start=1):
        connection.execute(
            text("UPDATE companies SET created_at = :t WHERE id = :id"),
            {"t": f"2026-01-0{day}T00:00:00Z", "id": row["id"]},
        )

    all_ids = [x["id"] for x in client.get(URL).json()]
    assert all_ids == [c["id"], b["id"], a["id"]]  # newest first

    # Search is case-insensitive and covers several fields (industry here).
    assert [x["id"] for x in client.get(URL, params={"search": "MANUFACT"}).json()] == [b["id"]]
    assert [x["id"] for x in client.get(URL, params={"status": "Inactive"}).json()] == [c["id"]]
    assert client.get(URL, params={"status": "Archived"}).status_code == 422


def test_search_treats_wildcards_literally(client):
    create(client, URL, company_payload(name="Plain Co"))
    pct = create(client, URL, company_payload(name="100% Growth"))
    assert [x["id"] for x in client.get(URL, params={"search": "%"}).json()] == [pct["id"]]
    assert client.get(URL, params={"search": "_"}).json() == []
