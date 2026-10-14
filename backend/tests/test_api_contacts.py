import uuid

import pytest

from tests.api_helpers import activity_payload, company_payload, contact_payload, create, error_fields

URL = "/api/contacts"


@pytest.fixture
def company(client):
    return create(client, "/api/companies", company_payload(name="Northwind Logistics"))


def test_create_maps_camelcase_fields(client, company):
    body = create(client, URL, contact_payload(company["id"], jobTitle="Chief Procurement Officer"))
    assert body["companyId"] == company["id"]
    assert body["jobTitle"] == "Chief Procurement Officer"
    assert "job_title" not in body and "company_id" not in body


def test_snake_case_input_is_rejected(client, company):
    payload = contact_payload(company["id"])
    payload["job_title"] = payload.pop("jobTitle")
    response = client.post(URL, json=payload)
    assert response.status_code == 422
    assert set(error_fields(response)) == {"jobTitle", "job_title"}  # missing + unknown


def test_missing_company_returns_422(client):
    response = client.post(URL, json=contact_payload(str(uuid.uuid4())))
    assert response.status_code == 422
    assert error_fields(response) == ["companyId"]


def test_duplicate_email_case_insensitive_returns_409(client, company):
    create(client, URL, contact_payload(company["id"], email="priya.raman@northwind.example"))
    response = client.post(URL, json=contact_payload(company["id"], email="Priya.Raman@NORTHWIND.example"))
    assert response.status_code == 409
    assert response.json() == {"detail": "A contact with this email already exists."}


def test_get_update_delete_and_missing(client, company):
    contact = create(client, URL, contact_payload(company["id"]))
    assert client.get(f"{URL}/{contact['id']}").json() == contact

    response = client.patch(f"{URL}/{contact['id']}", json={"jobTitle": "COO"})
    assert response.status_code == 200 and response.json()["jobTitle"] == "COO"

    assert client.delete(f"{URL}/{contact['id']}").status_code == 204
    assert client.get(f"{URL}/{contact['id']}").status_code == 404
    assert client.patch(f"{URL}/{contact['id']}", json={"name": "X"}).status_code == 404


def test_move_to_another_company_without_activities(client, company):
    other = create(client, "/api/companies", company_payload())
    contact = create(client, URL, contact_payload(company["id"]))
    response = client.patch(f"{URL}/{contact['id']}", json={"companyId": other["id"]})
    assert response.status_code == 200
    assert response.json()["companyId"] == other["id"]


def test_move_to_missing_company_returns_422(client, company):
    contact = create(client, URL, contact_payload(company["id"]))
    response = client.patch(f"{URL}/{contact['id']}", json={"companyId": str(uuid.uuid4())})
    assert response.status_code == 422


def test_move_contact_with_activities_returns_409(client, company):
    """Moving would leave activities pointing at a contact from another company."""
    other = create(client, "/api/companies", company_payload())
    contact = create(client, URL, contact_payload(company["id"]))
    create(client, "/api/activities", activity_payload(company["id"], contact["id"]))

    response = client.patch(f"{URL}/{contact['id']}", json={"companyId": other["id"]})
    assert response.status_code == 409
    assert client.get(f"{URL}/{contact['id']}").json()["companyId"] == company["id"]  # unchanged


def test_delete_contact_keeps_activity_and_clears_contact_id(client, company):
    contact = create(client, URL, contact_payload(company["id"]))
    activity = create(client, "/api/activities", activity_payload(company["id"], contact["id"]))

    assert client.delete(f"{URL}/{contact['id']}").status_code == 204
    response = client.get(f"/api/activities/{activity['id']}")
    assert response.status_code == 200
    assert response.json()["contactId"] is None


def test_list_filter_by_company_and_search_by_company_name(client, company):
    other = create(client, "/api/companies", company_payload(name="Helios Energy"))
    mine = create(client, URL, contact_payload(company["id"], name="Priya Raman"))
    theirs = create(client, URL, contact_payload(other["id"], name="Marcus Chen"))

    by_company = client.get(URL, params={"companyId": company["id"]}).json()
    assert [c["id"] for c in by_company] == [mine["id"]]

    by_company_name = client.get(URL, params={"search": "helios"}).json()
    assert [c["id"] for c in by_company_name] == [theirs["id"]]
