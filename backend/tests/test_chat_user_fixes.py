"""Failures seen when everyday-user prompts ran against the real model."""

import uuid

import pytest

from app.chat.agent import ANSWER_NOW, NOT_SAVED_YET

from tests.test_chat_api import FakeLLM, _isolation, ask, reply, tool_call, use_llm  # noqa: F401
from tests.api_helpers import company_payload, create, deal_payload
from tests.test_chat_tools import DATA, call, seeded  # noqa: F401


def labels(out):
    return [m["label"] for m in out["matches"]]


def test_words_from_company_and_subject_find_the_record(seeded):  # noqa: F811
    assert labels(call(seeded, "search", query="vertex demo")) == ["On-site demo with plant leadership"]


def test_filler_words_do_not_block_a_match(seeded):  # noqa: F811
    assert "Fleet tracking rollout" in labels(call(seeded, "search", query="the fleet thing"))


def test_win_rate_is_computed_by_the_database(seeded):  # noqa: F811
    won = sum(d["stage"] == "Won" for d in DATA["deals"])
    closed = won + sum(d["stage"] == "Lost" for d in DATA["deals"])
    out = call(seeded, "aggregate", entity="deal", metric="win_rate")
    assert out["rows"] == [{"group": None, "value": f"{100 * won / closed:.1f}", "count": closed}]
    none = call(seeded, "aggregate", entity="deal", metric="win_rate", filters={"stage": ["Lead"]})
    assert none["rows"][0]["value"] is None
    assert "error" in call(seeded, "aggregate", entity="company", metric="win_rate")


def propose_then_say(client, api_app, text):
    company = create(client, "/api/companies", company_payload(name="Summit Retail Group"))
    deal = create(client, "/api/deals", deal_payload(company["id"], title="Store rollout", stage="Proposal"))
    change = tool_call("propose_update", "c1", entity="deal", id=deal["id"], changes={"stage": "Won"})
    use_llm(api_app, FakeLLM(reply(None, change), reply(text)))
    return ask(client, "mark it won").json()["reply"]


@pytest.mark.parametrize(
    "claim",
    ["The deal's stage has been updated to **Won**.", "I've marked it as won.", "I have deleted it."],
)
def test_a_reply_never_claims_an_unconfirmed_change_was_made(client, api_app, claim):
    said = propose_then_say(client, api_app, claim)
    assert said == NOT_SAVED_YET


def test_record_ids_are_removed_from_the_reply(client, api_app):
    record = str(uuid.uuid4())
    use_llm(api_app, FakeLLM(reply(f"Closest is **Demo** - ID `{record}`\nAlso {record}.")))
    said = ask(client).json()["reply"]
    assert record not in said and "ID" not in said and "**Demo**" in said


def test_last_round_tells_the_model_to_answer_now(client, api_app, auth_settings):
    looping = reply(None, tool_call("search", "s", query="x"))
    steps = [looping] * (auth_settings.chat_max_tool_rounds - 1) + [reply("Here is what I found.")]
    fake = use_llm(api_app, FakeLLM(*steps))
    assert ask(client).json()["reply"] == "Here is what I found."
    assert fake.requests[-1]["messages"][-1] == {"role": "system", "content": ANSWER_NOW}
    assert fake.requests[-2]["messages"][-1]["role"] == "tool"
