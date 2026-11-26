"""Questions the assistant could not answer before: company filters, inactivity, top-N groups."""

from collections import defaultdict
from datetime import date, timedelta

from tests.test_chat_tools import COMPANY_NAME, DATA, OPEN, TODAY, call, money, seeded  # noqa: F401

INDUSTRY = {c["id"]: c["industry"] for c in DATA["companies"]}


def names(out):
    return sorted(r["name"] for r in out["rows"])


def test_deals_filter_by_company_industry_and_location(seeded):  # noqa: F811
    out = call(seeded, "list_records", entity="deal", filters={"industry": "energy"})
    assert [r["title"] for r in out["rows"]] == [d["title"] for d in DATA["deals"] if INDUSTRY[d["companyId"]] == "Energy"]
    out = call(seeded, "list_records", entity="deal", filters={"location": "Austin"})
    assert out["total"] == 1


def test_deal_value_grouped_by_company_industry(seeded):  # noqa: F811
    expected = defaultdict(int)
    for d in DATA["deals"]:
        expected[INDUSTRY[d["companyId"]]] += d["value"]
    out = call(seeded, "aggregate", entity="deal", metric="sum_value", group_by="industry")
    assert {r["group"]: r["value"] for r in out["rows"]} == {k: money(v) for k, v in expected.items()}


def test_aggregate_top_n_by_value(seeded):  # noqa: F811
    per_company = defaultdict(int)
    for d in DATA["deals"]:
        if d["stage"] in OPEN:
            per_company[COMPANY_NAME[d["companyId"]]] += d["value"]
    top = sorted(per_company.items(), key=lambda kv: -kv[1])[:3]
    out = call(
        seeded, "aggregate", entity="deal", metric="sum_value", group_by="company",
        filters={"stage": sorted(OPEN)}, sort="-value", limit=3,
    )
    assert [(r["group"], r["value"]) for r in out["rows"]] == [(n, money(v)) for n, v in top]
    assert out["totalGroups"] == len(per_company)


def test_aggregate_ascending_and_default_order(seeded):  # noqa: F811
    low = call(seeded, "aggregate", entity="deal", metric="sum_value", group_by="company", sort="value", limit=1)
    smallest = min(DATA["deals"], key=lambda d: d["value"])
    assert low["rows"][0]["group"] == COMPANY_NAME[smallest["companyId"]]
    default = call(seeded, "aggregate", entity="deal", metric="count", group_by="stage")
    assert [r["group"] for r in default["rows"]] == sorted(r["group"] for r in default["rows"])


def test_companies_with_no_activity_since(seeded):  # noqa: F811
    since = date(2026, 10, 10)
    recent = {a["companyId"] for a in DATA["activities"] if since.isoformat() <= a["dueDate"] <= TODAY.isoformat()}
    out = call(seeded, "list_records", entity="company", filters={"noActivitySince": since.isoformat()}, limit=25)
    assert recent  # sanity
    assert names(out) == sorted(c["name"] for c in DATA["companies"] if c["id"] not in recent)
    assert out["total"] == len(out["rows"])


def test_a_future_activity_does_not_count_as_contact(seeded):  # noqa: F811
    # BrightPath's only activity is after TODAY, so it still had no activity in the last 30 days.
    since = (TODAY - timedelta(days=30)).isoformat()
    out = call(seeded, "list_records", entity="company", filters={"noActivitySince": since}, limit=25)
    assert "BrightPath Clinics" in names(out)


def test_companies_with_and_without_open_deals(seeded):  # noqa: F811
    with_open = {d["companyId"] for d in DATA["deals"] if d["stage"] in OPEN}
    yes = call(seeded, "list_records", entity="company", filters={"hasOpenDeals": True}, limit=25)
    no = call(seeded, "aggregate", entity="company", metric="count", filters={"hasOpenDeals": False})
    assert names(yes) == sorted(COMPANY_NAME[i] for i in with_open)
    assert no["rows"][0]["value"] == len(DATA["companies"]) - len(with_open)


def test_aggregate_rejects_bad_sort_and_limit(seeded):  # noqa: F811
    assert "error" in call(seeded, "aggregate", entity="deal", metric="count", group_by="stage", sort="stage")
    assert "error" in call(seeded, "aggregate", entity="deal", metric="count", group_by="stage", limit=0)
