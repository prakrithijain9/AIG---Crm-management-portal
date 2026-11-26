"""Forgiving search: when exact "contains" finds nothing, offer the closest names."""

import pytest

from app.chat.fuzzy import closest, similarity
from app.chat.tools import run_tool
from tests.test_chat_tools import TODAY, seeded  # noqa: F401  (fixture)


def search(db, query, **args):
    return run_tool(db, "search", {"query": query, **args}, TODAY)


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("Helois", "Helios Energy"),  # swapped letters
        ("Northwnd Logistics", "Northwind Logistics"),  # dropped letter
        ("Harbor and Co", "Harbor & Co."),  # "&" and punctuation
        ("harbour", "Harbor & Co."),  # British spelling
        ("Logistics Northwind", "Northwind Logistics"),  # word order
        ("vertex manufacturing company", "Vertex Manufacturing"),  # filler word
    ],
)
def test_close_company_names_score_as_matches(query, name):
    assert similarity(query, name) >= 0.75


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("Acme Corporation", "Aperture Analytics"),
        ("plorp", "BrightPath Clinics"),
        ("the company", "Summit Retail Group"),  # only filler words
        ("%", "Lumen Media"),
        ("al", "David Hale"),  # too short to guess from
    ],
)
def test_unrelated_text_scores_low(query, name):
    assert similarity(query, name) < 0.75


def test_closest_ranks_best_first_and_caps():
    items = [("a", ["Helios Energy"]), ("b", ["Helix Energy"]), ("c", ["Lumen Media"])]
    assert closest("Helios Energy", items, limit=1) == ["a"]
    assert "c" not in closest("Helios", items)


def test_search_offers_suggestions_when_nothing_matches_exactly(seeded):  # noqa: F811
    out = search(seeded, "Helois", entity="company")
    assert out["matches"] == []
    assert [m["label"] for m in out["didYouMean"]] == ["Helios Energy"]
    assert out["didYouMean"][0]["id"] and out["didYouMean"][0]["companyName"] == "Helios Energy"
    assert out["sources"] == []  # a guess is not shown as a confirmed record


def test_search_suggests_a_misspelled_contact(seeded):  # noqa: F811
    out = search(seeded, "Priya Ramen")
    assert any(m["label"].startswith("Priya Raman") for m in out["didYouMean"])


def test_exact_matches_carry_no_suggestions(seeded):  # noqa: F811
    out = search(seeded, "Helios")
    assert out["matches"] and "didYouMean" not in out


def test_no_suggestions_for_unrelated_text(seeded):  # noqa: F811
    out = search(seeded, "zzz-no-such-thing")
    assert out["matches"] == [] and "didYouMean" not in out
