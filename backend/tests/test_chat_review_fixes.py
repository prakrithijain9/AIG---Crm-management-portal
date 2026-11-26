"""Problems found in review: noisy or wrong guesses, ties at a limit, odd filter values."""

from app.chat.fuzzy import similarity
from app.chat.tools import run_tool
from tests.test_chat_tools import TODAY, call, seeded  # noqa: F401


def guesses(db, query, **args):
    return [m["label"] for m in call(db, "search", query=query, **args).get("didYouMean", [])]


def test_company_typo_does_not_drag_in_its_deals_and_activities(seeded):  # noqa: F811
    assert guesses(seeded, "Northwnd") == ["Northwind Logistics"]


def test_deal_can_still_be_found_through_a_misspelled_company(seeded):  # noqa: F811
    assert guesses(seeded, "Helois", entity="deal") == ["Grid monitoring suite"]


def test_name_plus_misspelled_company_finds_the_contact(seeded):  # noqa: F811
    assert any(g.startswith("Priya Raman") for g in guesses(seeded, "Priya Northwnd"))


def test_numbers_must_match_exactly():
    assert similarity("Invoice 1042", "Invoice 1043") < 0.75
    assert similarity("FY2025 renewal", "FY2026 renewal") < 0.75


def test_split_words_and_plural_fillers():
    assert similarity("north wind", "Northwind Logistics") >= 0.75
    assert similarity("bright path", "BrightPath Clinics") >= 0.75
    assert similarity("helios contacts", "Helios Energy") >= 0.75


def test_limit_flags_a_tie_at_the_cutoff(seeded):  # noqa: F811
    out = call(seeded, "aggregate", entity="deal", metric="count", group_by="stage", sort="-value", limit=1)
    assert out["tiedAtCutoff"] is True
    out = call(seeded, "aggregate", entity="deal", metric="sum_value", group_by="company", sort="-value", limit=1)
    assert out["tiedAtCutoff"] is False


def test_two_letter_location_is_a_state_code_not_any_substring(seeded):  # noqa: F811
    out = call(seeded, "list_records", entity="company", filters={"location": "CA"}, limit=25)
    assert sorted(r["name"] for r in out["rows"]) == ["Lumen Media", "Northwind Logistics"]  # not Chicago
    assert call(seeded, "list_records", entity="company", filters={"location": "Chicago"})["total"] == 1


def test_no_activity_since_a_future_date_is_an_error(seeded):  # noqa: F811
    out = run_tool(seeded, "list_records", {"entity": "company", "filters": {"noActivitySince": "2027-01-01"}}, TODAY)
    assert "future" in out["error"]
