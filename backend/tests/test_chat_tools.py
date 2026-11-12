"""Chat tools against the real test database, seeded with the demo data.

Expected numbers are computed here in plain Python from demo_data.json, never from the
code under test, so a wrong SQL filter or sum fails the test.
"""

import json
import uuid
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.chat.tools import TOOLS, run_tool, tool_specs
from app.models import Activity, Company, Contact, Deal
from app.seed.demo import load_demo_data, seed_demo_data

DATA = load_demo_data()
TODAY = date(2026, 10, 14)
COMPANY_NAME = {c["id"]: c["name"] for c in DATA["companies"]}
OPEN = {"Lead", "Qualified", "Proposal", "Negotiation"}


def money(x) -> str:
    return f"{Decimal(str(x)):.2f}"


@pytest.fixture
def seeded(db):
    seed_demo_data(db, apply=True)
    return db


def call(db, name, **args):
    return run_tool(db, name, args, TODAY)


def cid(db, name):
    return str(db.scalar(select(Company.id).where(Company.name == name)))


def row_counts(db):
    return [db.scalar(select(func.count()).select_from(m)) for m in (Company, Contact, Deal, Activity)]


# --- registry -------------------------------------------------------------------------


def test_every_tool_has_a_flat_json_schema():
    specs = tool_specs()
    assert {s["function"]["name"] for s in specs} == set(TOOLS) and len(specs) == 8
    text = json.dumps(specs)
    assert "$ref" not in text and "$defs" not in text


def test_unknown_tool_bad_json_and_extra_args_become_errors(seeded):
    assert "Unknown tool" in run_tool(seeded, "drop_tables", {}, TODAY)["error"]
    assert "JSON" in run_tool(seeded, "search", "{not json", TODAY)["error"]
    assert "error" in call(seeded, "search", query="x", bogus=1)
    assert "error" in call(seeded, "search")  # missing query


# --- counts and sums come from SQL ----------------------------------------------------


def test_list_total_ignores_limit(seeded):
    out = call(seeded, "list_records", entity="deal", limit=2)
    assert out["total"] == len(DATA["deals"]) == 8
    assert out["returned"] == len(out["rows"]) == 2


def test_deal_sum_and_avg_match_python(seeded):
    values = [Decimal(str(d["value"])) for d in DATA["deals"]]
    total = call(seeded, "aggregate", entity="deal", metric="sum_value")
    assert total["rows"] == [{"group": None, "value": money(sum(values)), "count": 8}]
    avg = call(seeded, "aggregate", entity="deal", metric="avg_value")
    assert avg["rows"][0]["value"] == money(sum(values) / len(values))


def test_deal_sum_by_stage(seeded):
    expected = defaultdict(Decimal)
    for d in DATA["deals"]:
        expected[d["stage"]] += Decimal(str(d["value"]))
    out = call(seeded, "aggregate", entity="deal", metric="sum_value", group_by="stage")
    assert {r["group"]: r["value"] for r in out["rows"]} == {k: money(v) for k, v in expected.items()}


def test_open_pipeline_with_stage_filter(seeded):
    expected = sum(Decimal(str(d["value"])) for d in DATA["deals"] if d["stage"] in OPEN)
    out = call(
        seeded, "aggregate", entity="deal", metric="sum_value",
        filters={"stage": ["Lead", "Qualified", "Proposal", "Negotiation"]},
    )
    assert out["rows"][0]["value"] == money(expected)


def test_deal_filters_value_and_close_date(seeded):
    big = [d for d in DATA["deals"] if d["value"] >= 200000]
    out = call(seeded, "list_records", entity="deal", filters={"valueMin": 200000})
    assert out["total"] == len(big)
    in_nov = [d for d in DATA["deals"] if "2026-11-01" <= d["expectedCloseDate"] <= "2026-11-30"]
    out = call(seeded, "list_records", entity="deal", filters={"closeFrom": "2026-11-01", "closeTo": "2026-11-30"})
    assert out["total"] == len(in_nov)
    by_month = call(seeded, "aggregate", entity="deal", metric="count", group_by="close_month")
    expected = Counter(d["expectedCloseDate"][:7] for d in DATA["deals"])
    assert {r["group"]: r["value"] for r in by_month["rows"]} == dict(expected)


def test_deal_row_value_is_a_two_decimal_string(seeded):
    out = call(seeded, "list_records", entity="deal", filters={"search": "Grid monitoring"})
    assert out["total"] == 1
    assert out["rows"][0]["value"] == "420000.00"
    assert out["rows"][0]["companyName"] == COMPANY_NAME["cmp-2"]


def test_overdue_activities_use_today_and_pending_only(seeded):
    expected = [a for a in DATA["activities"] if a["status"] == "Pending" and a["dueDate"] < TODAY.isoformat()]
    assert len(expected) == 2  # sanity: 2026-10-13 and 2026-10-12
    out = call(seeded, "list_records", entity="activity", filters={"overdue": True})
    assert out["total"] == len(expected)
    assert {r["subject"] for r in out["rows"]} == {a["subject"] for a in expected}


def test_activity_date_range_and_type_filters(seeded):
    expected = [a for a in DATA["activities"] if a["type"] == "Meeting"]
    out = call(seeded, "list_records", entity="activity", filters={"type": "Meeting"})
    assert out["total"] == len(expected)
    ranged = [a for a in DATA["activities"] if "2026-10-12" <= a["dueDate"] <= "2026-10-14"]
    out = call(seeded, "list_records", entity="activity", filters={"dueFrom": "2026-10-12", "dueTo": "2026-10-14"})
    assert out["total"] == len(ranged)


def test_counts_by_status_and_company(seeded):
    by_status = call(seeded, "aggregate", entity="company", metric="count", group_by="status")
    assert {r["group"]: r["value"] for r in by_status["rows"]} == dict(Counter(c["status"] for c in DATA["companies"]))
    per_company = call(seeded, "aggregate", entity="contact", metric="count", group_by="company")
    expected = Counter(COMPANY_NAME[c["companyId"]] for c in DATA["contacts"])
    assert {r["group"]: r["value"] for r in per_company["rows"]} == dict(expected)
    by_type = call(seeded, "aggregate", entity="activity", metric="count", group_by="type")
    assert {r["group"]: r["value"] for r in by_type["rows"]} == dict(Counter(a["type"] for a in DATA["activities"]))


def test_plain_count_for_every_entity(seeded):
    for entity, key in (("company", "companies"), ("contact", "contacts"), ("deal", "deals"), ("activity", "activities")):
        out = call(seeded, "aggregate", entity=entity, metric="count")
        assert out["rows"][0]["value"] == len(DATA[key])


def test_list_sorting(seeded):
    out = call(seeded, "list_records", entity="deal", sort="-value", limit=3)
    top = sorted(DATA["deals"], key=lambda d: -d["value"])[:3]
    assert [r["title"] for r in out["rows"]] == [d["title"] for d in top]
    assert "error" in call(seeded, "list_records", entity="deal", sort="nonsense")


def test_invalid_aggregate_and_filter_requests_return_errors(seeded):
    assert "only available for deals" in call(seeded, "aggregate", entity="company", metric="sum_value")["error"]
    assert "group_by" in call(seeded, "aggregate", entity="deal", metric="count", group_by="color")["error"]
    bad = call(seeded, "list_records", entity="deal", filters={"stage": ["Nope"]})
    assert "error" in bad and "stage.0" in bad["fieldErrors"]
    assert "error" in call(seeded, "list_records", entity="deal", filters={"title": "x"})
    assert "error" in call(seeded, "list_records", entity="deal", limit=1000)


# --- search and get_record -----------------------------------------------------------


def test_search_finds_across_entities_and_reports_company(seeded):
    out = call(seeded, "search", query="northwind")
    types = {m["type"] for m in out["matches"]}
    assert "company" in types and "contact" in types  # contacts match on the northwind.example email
    company = next(m for m in out["matches"] if m["type"] == "company")
    assert company["label"] == "Northwind Logistics" and company["companyName"] == "Northwind Logistics"
    assert len(out["sources"]) == len(out["matches"])


def test_search_entity_filter_and_no_match(seeded):
    only = call(seeded, "search", query="Priya", entity="contact")
    assert [m["type"] for m in only["matches"]] == ["contact"]
    assert call(seeded, "search", query="zzz-no-such-thing")["matches"] == []


def test_search_treats_percent_literally(seeded):
    assert call(seeded, "search", query="%")["matches"] == []


def test_search_caps_at_ten_and_flags_truncation(seeded):
    out = call(seeded, "search", query="a")  # matches almost everything
    assert len(out["matches"]) == 10 and out["truncated"] is True


def test_get_company_related_counts(seeded):
    company_id = cid(seeded, "Northwind Logistics")
    out = call(seeded, "get_record", entity="company", id=company_id)
    deals = [d for d in DATA["deals"] if d["companyId"] == "cmp-1"]
    open_value = sum(Decimal(str(d["value"])) for d in deals if d["stage"] in OPEN)
    assert out["related"] == {
        "contacts": len([c for c in DATA["contacts"] if c["companyId"] == "cmp-1"]),
        "deals": len(deals),
        "openDeals": len([d for d in deals if d["stage"] in OPEN]),
        "openPipelineValue": money(open_value),
        "pendingActivities": len(
            [a for a in DATA["activities"] if a["companyId"] == "cmp-1" and a["status"] == "Pending"]
        ),
    }
    assert out["record"]["name"] == "Northwind Logistics"


def test_get_activity_includes_names_and_missing_id_errors(seeded):
    act = seeded.scalar(select(Activity).where(Activity.subject == "Closed-lost debrief"))
    out = call(seeded, "get_record", entity="activity", id=str(act.id))
    assert out["record"]["companyName"] == COMPANY_NAME["cmp-6"]
    assert out["record"]["contactName"]
    assert "No activity" in call(seeded, "get_record", entity="activity", id=str(uuid.uuid4()))["error"]
    assert "error" in call(seeded, "get_record", entity="deal", id="not-a-uuid")


# --- proposals never write ------------------------------------------------------------


def test_propose_create_deal_returns_full_camelcase_input(seeded):
    before = row_counts(seeded)
    out = call(
        seeded, "propose_create", entity="deal",
        fields={"title": "New deal", "companyId": cid(seeded, "Northwind Logistics"), "value": 1234.5,
                "expectedCloseDate": "2026-12-01"},
    )
    assert out["op"] == "create" and uuid.UUID(out["proposalId"])
    assert out["input"]["stage"] == "Lead"  # schema default filled in
    assert out["input"]["value"] == 1234.5
    assert set(out["input"]) == {"title", "companyId", "value", "stage", "expectedCloseDate"}
    assert out["summary"].startswith('Create deal "New deal"')
    assert row_counts(seeded) == before


@pytest.mark.parametrize(
    ("entity", "fields_for", "bad_field"),
    [
        ("deal", lambda c: {"title": "x", "companyId": c, "value": -5, "expectedCloseDate": "2026-12-01"}, "value"),
        ("deal", lambda c: {"title": "x", "companyId": str(uuid.uuid4()), "value": 1, "expectedCloseDate": "2026-12-01"}, "companyId"),
        ("deal", lambda c: {"title": "x", "companyId": c, "value": 1}, "expectedCloseDate"),
        ("company", lambda c: {"name": "Northwind LOGISTICS", "industry": "i", "email": "a@b.co", "phone": "1", "location": "l"}, "name"),
        ("contact", lambda c: {"name": "n", "companyId": c, "email": "PRIYA.RAMAN@northwind.example", "phone": "1", "jobTitle": "j"}, "email"),
        ("contact", lambda c: {"name": "n", "companyId": c, "email": "not-an-email", "phone": "1", "jobTitle": "j"}, "email"),
    ],
)
def test_invalid_create_proposals_error_and_write_nothing(seeded, entity, fields_for, bad_field):
    before = row_counts(seeded)
    out = call(seeded, "propose_create", entity=entity, fields=fields_for(cid(seeded, "Northwind Logistics")))
    assert "error" in out and bad_field in out["fieldErrors"]
    assert "proposalId" not in out
    assert row_counts(seeded) == before


def test_error_messages_never_echo_the_submitted_values(seeded):
    secret = "super-secret-value-123"
    out = call(seeded, "propose_create", entity="contact", fields={"email": secret, "bogusField": secret})
    assert secret not in json.dumps(out)


def test_activity_contact_must_belong_to_the_company(seeded):
    other_contact = seeded.scalar(select(Contact.id).where(Contact.company_id == uuid.UUID(cid(seeded, "Northwind Logistics"))))
    out = call(
        seeded, "propose_create", entity="activity",
        fields={"type": "Call", "subject": "x", "companyId": cid(seeded, COMPANY_NAME["cmp-2"]),
                "contactId": str(other_contact), "dueDate": "2026-11-01"},
    )
    assert "different company" in out["fieldErrors"]["contactId"]


def test_propose_update_stage_summary_and_full_input(seeded):
    deal = seeded.scalar(select(Deal).where(Deal.title == "Grid monitoring suite"))
    before = row_counts(seeded)
    out = call(seeded, "propose_update", entity="deal", id=str(deal.id), changes={"stage": "Won"})
    assert out["summary"] == 'Update deal "Grid monitoring suite": stage Proposal → Won'
    assert out["before"]["stage"] == "Proposal"
    assert out["input"]["stage"] == "Won"
    assert out["input"]["title"] == "Grid monitoring suite" and out["input"]["value"] == 420000.0  # full input
    assert row_counts(seeded) == before
    assert seeded.get(Deal, deal.id).stage == "Proposal"  # DB untouched


def test_propose_update_rejects_noop_unknown_field_and_null(seeded):
    deal = seeded.scalar(select(Deal).where(Deal.title == "Grid monitoring suite"))
    assert "No changes" in call(seeded, "propose_update", entity="deal", id=str(deal.id), changes={"stage": "Proposal"})["error"]
    assert "error" in call(seeded, "propose_update", entity="deal", id=str(deal.id), changes={"colour": "red"})
    assert "error" in call(seeded, "propose_update", entity="deal", id=str(deal.id), changes={"title": None})
    assert "No deal" in call(seeded, "propose_update", entity="deal", id=str(uuid.uuid4()), changes={"stage": "Won"})["error"]


def test_propose_update_company_name_collision_is_rejected_but_own_name_is_fine(seeded):
    company = seeded.scalar(select(Company).where(Company.name == "Northwind Logistics"))
    other = COMPANY_NAME["cmp-2"]
    bad = call(seeded, "propose_update", entity="company", id=str(company.id), changes={"name": other.upper()})
    assert "name" in bad["fieldErrors"]
    ok = call(seeded, "propose_update", entity="company", id=str(company.id),
              changes={"name": "Northwind Logistics", "industry": "Freight"})
    assert ok["summary"].endswith("industry Transportation → Freight")


def test_propose_update_activity_can_unlink_contact(seeded):
    act = seeded.scalar(select(Activity).where(Activity.subject == "Closed-lost debrief"))
    out = call(seeded, "propose_update", entity="activity", id=str(act.id), changes={"contactId": None})
    assert out["input"]["contactId"] is None and "contactId" in out["summary"]


def test_propose_delete_company_reports_cascade_counts(seeded):
    out = call(seeded, "propose_delete", entity="company", id=cid(seeded, "Northwind Logistics"))
    expect = {
        "contacts": len([c for c in DATA["contacts"] if c["companyId"] == "cmp-1"]),
        "deals": len([d for d in DATA["deals"] if d["companyId"] == "cmp-1"]),
        "activities": len([a for a in DATA["activities"] if a["companyId"] == "cmp-1"]),
    }
    assert out["impact"] == expect
    assert f'{expect["contacts"]} contacts' in out["summary"]
    assert row_counts(seeded) == [8, 10, 8, 8]  # nothing deleted


def test_propose_delete_contact_reports_activities_losing_it(seeded):
    contact = seeded.scalar(select(Contact).where(Contact.email == "priya.raman@northwind.example"))
    out = call(seeded, "propose_delete", entity="contact", id=str(contact.id))
    expected = len([a for a in DATA["activities"] if a["contactId"] == "ct-1"])
    assert out["impact"] == {"activitiesLosingContact": expected}
    deal = seeded.scalar(select(Deal))
    assert call(seeded, "propose_delete", entity="deal", id=str(deal.id))["impact"] is None
    assert "No contact" in call(seeded, "propose_delete", entity="contact", id=str(uuid.uuid4()))["error"]


# --- navigation -----------------------------------------------------------------------


def test_navigate_builds_validated_hrefs(seeded):
    assert call(seeded, "navigate", page="dashboard")["action"]["href"] == "/"
    assert call(seeded, "navigate", page="deals")["action"]["href"] == "/deals"
    out = call(seeded, "navigate", page="deals", filters={"stage": "Won"})["action"]
    assert out == {"type": "navigate", "label": "Open Deals (stage: Won)", "href": "/deals?stage=Won"}
    out = call(seeded, "navigate", page="contacts", filters={"search": "a&b c"})["action"]
    assert out["href"] == "/contacts?search=a%26b+c"


def test_navigate_open_record_uses_server_label_and_checks_existence(seeded):
    deal = seeded.scalar(select(Deal).where(Deal.title == "Grid monitoring suite"))
    out = call(seeded, "navigate", page="deals", openId=str(deal.id))["action"]
    assert out["href"] == f"/deals?open={deal.id}"
    assert out["label"] == 'Open deal "Grid monitoring suite"'
    assert "No deal" in call(seeded, "navigate", page="deals", openId=str(uuid.uuid4()))["error"]
    assert "dashboard" in call(seeded, "navigate", page="dashboard", openId=str(deal.id))["error"]


def test_navigate_rejects_unknown_filters_and_values(seeded):
    assert "not available" in call(seeded, "navigate", page="deals", filters={"status": "Won"})["error"]
    assert "Invalid value" in call(seeded, "navigate", page="deals", filters={"stage": "Maybe"})["error"]
    assert "error" in call(seeded, "navigate", page="admin")


def test_value_bounds_are_inclusive(seeded):
    exact = 420000  # Grid monitoring suite is exactly this value
    lo = call(seeded, "list_records", entity="deal", filters={"valueMin": exact})
    hi = call(seeded, "list_records", entity="deal", filters={"valueMax": exact})
    assert lo["total"] == len([d for d in DATA["deals"] if d["value"] >= exact]) == 1
    assert hi["total"] == len([d for d in DATA["deals"] if d["value"] <= exact]) == 8
