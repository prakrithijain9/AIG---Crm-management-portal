import uuid

import pytest

from tests.api_helpers import company_payload, create, deal_payload, error_fields

URL = "/api/deals"


@pytest.fixture
def company(client):
    return create(client, "/api/companies", company_payload(name="Summit Retail Group"))


def test_create_value_is_a_json_number_and_date_is_iso(client, company):
    body = create(client, URL, deal_payload(company["id"], value=125000.5, expectedCloseDate="2026-12-01"))
    assert body["value"] == 125000.5 and isinstance(body["value"], float)
    assert body["expectedCloseDate"] == "2026-12-01"
    assert body["companyId"] == company["id"]


def test_stage_defaults_to_lead(client, company):
    payload = deal_payload(company["id"])
    del payload["stage"]
    assert create(client, URL, payload)["stage"] == "Lead"


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"value": -1}, "value"),
        ({"value": 10.123}, "value"),  # more than 2 decimal places
        ({"value": "lots"}, "value"),
        ({"stage": "Closed"}, "stage"),
        ({"expectedCloseDate": "2026-13-40"}, "expectedCloseDate"),
        ({"title": ""}, "title"),
    ],
)
def test_validation_errors(client, company, override, field):
    response = client.post(URL, json=deal_payload(company["id"], **override))
    assert response.status_code == 422
    assert field in error_fields(response)


def test_missing_company_returns_422(client):
    response = client.post(URL, json=deal_payload(str(uuid.uuid4())))
    assert response.status_code == 422
    assert error_fields(response) == ["companyId"]


def test_update_stage_and_value(client, company):
    deal = create(client, URL, deal_payload(company["id"]))
    response = client.patch(f"{URL}/{deal['id']}", json={"stage": "Won", "value": 200000})
    assert response.status_code == 200
    assert (response.json()["stage"], response.json()["value"]) == ("Won", 200000.0)


def test_update_to_missing_company_returns_422(client, company):
    deal = create(client, URL, deal_payload(company["id"]))
    assert client.patch(f"{URL}/{deal['id']}", json={"companyId": str(uuid.uuid4())}).status_code == 422


def test_get_delete_and_missing(client, company):
    deal = create(client, URL, deal_payload(company["id"]))
    assert client.get(f"{URL}/{deal['id']}").json() == deal
    assert client.delete(f"{URL}/{deal['id']}").status_code == 204
    assert client.get(f"{URL}/{deal['id']}").status_code == 404
    assert client.delete(f"{URL}/{deal['id']}").status_code == 404


def test_list_filter_by_stage_company_and_search(client, company):
    other = create(client, "/api/companies", company_payload(name="Vertex Manufacturing"))
    won = create(client, URL, deal_payload(company["id"], title="Store rollout", stage="Won"))
    lead = create(client, URL, deal_payload(other["id"], title="Plant automation", stage="Lead"))

    assert [d["id"] for d in client.get(URL, params={"stage": "Won"}).json()] == [won["id"]]
    assert [d["id"] for d in client.get(URL, params={"companyId": other["id"]}).json()] == [lead["id"]]
    # Search covers the company name and the stage.
    assert [d["id"] for d in client.get(URL, params={"search": "vertex"}).json()] == [lead["id"]]
    assert [d["id"] for d in client.get(URL, params={"search": "won"}).json()] == [won["id"]]
