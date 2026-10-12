import uuid

import pytest

from tests.api_helpers import activity_payload, company_payload, contact_payload, create, error_fields

URL = "/api/activities"


@pytest.fixture
def company(client):
    return create(client, "/api/companies", company_payload(name="BrightPath Clinics"))


@pytest.fixture
def contact(client, company):
    return create(client, "/api/contacts", contact_payload(company["id"], name="Elena Vasquez"))


@pytest.fixture
def other_company_contact(client):
    other = create(client, "/api/companies", company_payload(name="Lumen Media"))
    return create(client, "/api/contacts", contact_payload(other["id"], name="Sam Lee"))


def test_create_with_contact_from_same_company(client, company, contact):
    body = create(client, URL, activity_payload(company["id"], contact["id"], type="Follow-up"))
    assert (body["companyId"], body["contactId"], body["type"]) == (company["id"], contact["id"], "Follow-up")
    assert body["dueDate"] == "2026-10-20"


def test_create_without_contact_and_default_status(client, company):
    payload = activity_payload(company["id"])
    del payload["status"]
    body = create(client, URL, payload)
    assert body["contactId"] is None
    assert body["status"] == "Pending"


def test_contact_from_another_company_returns_422(client, company, other_company_contact):
    response = client.post(URL, json=activity_payload(company["id"], other_company_contact["id"]))
    assert response.status_code == 422
    assert error_fields(response) == ["contactId"]
    assert "different company" in response.json()["detail"][0]["msg"]


def test_missing_contact_or_company_returns_422(client, company):
    response = client.post(URL, json=activity_payload(company["id"], str(uuid.uuid4())))
    assert response.status_code == 422 and error_fields(response) == ["contactId"]
    response = client.post(URL, json=activity_payload(str(uuid.uuid4())))
    assert response.status_code == 422 and error_fields(response) == ["companyId"]


@pytest.mark.parametrize(
    ("override", "field"),
    [({"type": "Lunch"}, "type"), ({"status": "Done"}, "status"), ({"subject": " "}, "subject"), ({"dueDate": "soon"}, "dueDate")],
)
def test_validation_errors(client, company, override, field):
    response = client.post(URL, json=activity_payload(company["id"], **override))
    assert response.status_code == 422
    assert field in error_fields(response)


def test_update_status_and_unlink_contact(client, company, contact):
    activity = create(client, URL, activity_payload(company["id"], contact["id"]))
    response = client.patch(f"{URL}/{activity['id']}", json={"status": "Completed", "contactId": None})
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["contactId"]) == ("Completed", None)


def test_update_cannot_null_required_fields(client, company):
    activity = create(client, URL, activity_payload(company["id"]))
    assert client.patch(f"{URL}/{activity['id']}", json={"dueDate": None}).status_code == 422


def test_update_to_other_company_contact_returns_422(client, company, other_company_contact):
    activity = create(client, URL, activity_payload(company["id"]))
    response = client.patch(f"{URL}/{activity['id']}", json={"contactId": other_company_contact["id"]})
    assert response.status_code == 422


def test_changing_company_checks_existing_contact(client, company, contact):
    """Changing only companyId must still be consistent with the contact already linked."""
    other = create(client, "/api/companies", company_payload())
    activity = create(client, URL, activity_payload(company["id"], contact["id"]))

    response = client.patch(f"{URL}/{activity['id']}", json={"companyId": other["id"]})
    assert response.status_code == 422 and error_fields(response) == ["contactId"]

    # Moving company and clearing the contact together is fine.
    response = client.patch(f"{URL}/{activity['id']}", json={"companyId": other["id"], "contactId": None})
    assert response.status_code == 200 and response.json()["companyId"] == other["id"]


def test_get_delete_and_missing(client, company):
    activity = create(client, URL, activity_payload(company["id"]))
    assert client.get(f"{URL}/{activity['id']}").json() == activity
    assert client.delete(f"{URL}/{activity['id']}").status_code == 204
    assert client.get(f"{URL}/{activity['id']}").status_code == 404
    assert client.patch(f"{URL}/{activity['id']}", json={"subject": "X"}).status_code == 404


def test_list_sorted_by_due_date_with_filters_and_search(client, company, contact):
    later = create(client, URL, activity_payload(company["id"], dueDate="2026-11-05", subject="Quarterly review"))
    sooner = create(
        client, URL, activity_payload(company["id"], contact["id"], dueDate="2026-10-15", type="Meeting", status="Completed")
    )

    assert [a["id"] for a in client.get(URL).json()] == [sooner["id"], later["id"]]
    assert [a["id"] for a in client.get(URL, params={"status": "Completed"}).json()] == [sooner["id"]]
    assert [a["id"] for a in client.get(URL, params={"type": "Meeting"}).json()] == [sooner["id"]]
    assert [a["id"] for a in client.get(URL, params={"contactId": contact["id"]}).json()] == [sooner["id"]]
    assert len(client.get(URL, params={"companyId": company["id"]}).json()) == 2
    # Search matches the contact's name and the company's name.
    assert [a["id"] for a in client.get(URL, params={"search": "elena"}).json()] == [sooner["id"]]
    assert len(client.get(URL, params={"search": "brightpath"}).json()) == 2
