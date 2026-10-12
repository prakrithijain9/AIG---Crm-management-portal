"""Payload builders and small helpers for API tests (camelCase, like the frontend sends)."""

import itertools

from fastapi.testclient import TestClient

_seq = itertools.count(1)


def company_payload(**overrides) -> dict:
    n = next(_seq)
    return {
        "name": f"Company {n}",
        "industry": "Software",
        "email": f"hello{n}@company{n}.example",
        "phone": "+1 (206) 555-0133",
        "location": "Seattle, WA",
        "status": "Active",
    } | overrides


def contact_payload(company_id: str, **overrides) -> dict:
    n = next(_seq)
    return {
        "name": f"Person {n}",
        "companyId": company_id,
        "email": f"person{n}@contact.example",
        "phone": "+1 (415) 555-2210",
        "jobTitle": "VP of Operations",
    } | overrides


def deal_payload(company_id: str, **overrides) -> dict:
    return {
        "title": "Fleet expansion",
        "companyId": company_id,
        "value": 186000,
        "stage": "Proposal",
        "expectedCloseDate": "2026-10-22",
    } | overrides


def activity_payload(company_id: str, contact_id: str | None = None, **overrides) -> dict:
    return {
        "type": "Call",
        "subject": "Discovery call",
        "companyId": company_id,
        "contactId": contact_id,
        "dueDate": "2026-10-20",
        "status": "Pending",
    } | overrides


def create(client: TestClient, path: str, payload: dict) -> dict:
    response = client.post(path, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def error_fields(response) -> list[str]:
    """The camelCase field names a 422 response complains about."""
    return [str(err["loc"][-1]) for err in response.json()["detail"]]
