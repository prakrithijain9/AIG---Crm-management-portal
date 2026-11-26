"""Every chat request leaves one JSON line that says what was asked, done, queried and answered."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.chat.chatlog import ChatTrace, read_entries, write_trace
from app.core.config import Settings
from tests.api_helpers import company_payload, create, deal_payload
from tests.test_chat_api import (  # noqa: F401
    FakeLLM,
    _isolation,
    _rate_limited,
    ask,
    reply,
    tool_call,
    use_llm,
    with_settings,
)


@pytest.fixture
def log_dir(tmp_path, api_app, auth_settings):
    with_settings(api_app, auth_settings, chat_log_enabled=True, chat_log_dir=str(tmp_path))
    return tmp_path


def entries(log_dir):
    return [json.loads(line) for f in sorted(log_dir.glob("*.jsonl")) for line in f.read_text("utf-8").splitlines()]


def kinds(entry):
    return [e["type"] for e in entry["events"]]


def test_one_entry_records_prompt_model_calls_tools_sql_and_replies(client, api_app, log_dir):
    company = create(client, "/api/companies", company_payload(name="Summit Retail Group"))
    deal = create(client, "/api/deals", deal_payload(company["id"], title="Store rollout", stage="Proposal"))
    use_llm(
        api_app,
        FakeLLM(
            reply(None, tool_call("search", "c1", query="Summit")),
            reply(None, tool_call("propose_update", "c2", entity="deal", id=deal["id"], changes={"stage": "Won"})),
            reply("I've marked it as won."),
        ),
    )
    history = [{"role": "user", "content": "earlier"}]
    body = client.post(
        "/api/chat", json={"message": "mark it won", "history": history, "conversationId": "conv-1"}
    ).json()

    (entry,) = entries(log_dir)
    assert entry["conversationId"] == "conv-1" and entry["source"] == "app" and entry["adminId"]
    assert entry["message"] == "mark it won" and entry["history"] == history
    assert entry["status"] == "ok" and entry["durationMs"] >= 0 and entry["promptVersion"]
    assert entry["modelReply"] == "I've marked it as won."  # what the model said
    assert entry["reply"] == body["reply"] != entry["modelReply"]  # what the user saw
    assert entry["proposals"][0]["summary"].startswith('Update deal "Store rollout"')

    assert kinds(entry) == ["model", "tool", "model", "tool", "model"]
    model, tool = entry["events"][0], entry["events"][1]
    assert model["model"].startswith("groq:") and model["toolCalls"][0]["name"] == "search" and "ms" in model
    assert tool["name"] == "search" and json.loads(tool["arguments"]) == {"query": "Summit"}
    assert tool["result"]["matches"] and "ms" in tool
    assert any("FROM companies" in q["sql"] for q in tool["sql"])
    assert any("Summit" in json.dumps(q["params"]) for q in tool["sql"])


def test_token_use_is_recorded_when_the_provider_reports_it(client, api_app, log_dir):
    answer = reply("hello")
    answer.usage = SimpleNamespace(prompt_tokens=120, completion_tokens=7, total_tokens=127)
    use_llm(api_app, FakeLLM(answer))
    ask(client)
    assert entries(log_dir)[0]["events"][0]["tokens"] == {"prompt": 120, "completion": 7, "total": 127}


def test_failed_requests_are_logged_too(client, api_app, log_dir):
    use_llm(api_app, FakeLLM(_rate_limited()))
    assert ask(client).status_code == 429
    (entry,) = entries(log_dir)
    assert entry["status"] == "busy" and entry["events"][0]["error"].startswith("RateLimitError")


@pytest.mark.parametrize("enabled", [False, True])
def test_logging_can_be_off_and_a_broken_log_never_breaks_the_chat(client, api_app, auth_settings, tmp_path, enabled):
    target = tmp_path / "file"
    target.write_text("not a directory")  # writing here must fail
    with_settings(api_app, auth_settings, chat_log_enabled=enabled, chat_log_dir=str(target))
    use_llm(api_app, FakeLLM(reply("hello")))
    assert ask(client).json()["reply"] == "hello"
    assert target.read_text() == "not a directory"


def test_api_keys_are_masked(tmp_path):
    trace = ChatTrace(message="my key is gsk_abcdefghij1234567890 and AIzaSyA1234567890abcdefghij")
    write_trace(trace, tmp_path, retention_days=14)
    text = next(tmp_path.glob("*.jsonl")).read_text("utf-8")
    assert "gsk_abcdef" not in text and "AIzaSyA12345" not in text and "[key removed]" in text


@pytest.mark.parametrize("before", ["\n", "\t", "GROQ_", '"', "="])
def test_api_keys_are_masked_whatever_comes_before_them(tmp_path, before):
    write_trace(ChatTrace(message=f"key:{before}gsk_abcdefghij1234567890"), tmp_path, retention_days=14)
    assert "gsk_abcdef" not in next(tmp_path.glob("*.jsonl")).read_text("utf-8")


def test_ordinary_words_containing_sk_are_not_masked(tmp_path):
    write_trace(ChatTrace(message="risk-assessment-and-planning"), tmp_path, retention_days=14)
    assert "risk-assessment-and-planning" in next(tmp_path.glob("*.jsonl")).read_text("utf-8")


def test_reader_survives_line_separators_and_a_half_written_line(tmp_path):
    pasted = "a b c\u0085d"
    write_trace(ChatTrace(message=pasted), tmp_path, retention_days=14)
    path = next(tmp_path.glob("*.jsonl"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"cut off\n')
    found, unreadable = read_entries(path)
    assert [e["message"] for e in found] == [pasted] and unreadable == 1


def test_a_failing_query_is_still_recorded():
    trace = ChatTrace(message="hi")
    engine = create_engine("sqlite://")

    def broken() -> dict:
        with engine.connect() as connection:
            connection.execute(text("SELECT * FROM no_such_table"))
        return {}

    with pytest.raises(OperationalError):
        trace.run_tool("search", "{}", broken)
    (query,) = trace.data["events"][0]["sql"]
    assert "no_such_table" in query["sql"] and query["error"].startswith("OperationalError")


def test_rate_limited_requests_are_logged_without_their_history(client, api_app, auth_settings, log_dir):
    with_settings(
        api_app, auth_settings, chat_log_enabled=True, chat_log_dir=str(log_dir), chat_rate_limit_per_min=1
    )
    use_llm(api_app, FakeLLM(reply("hello")))
    body = {"message": "hi", "history": [{"role": "user", "content": "earlier"}]}
    client.post("/api/chat", json=body)
    assert client.post("/api/chat", json=body).status_code == 429
    last = entries(log_dir)[-1]
    assert last["status"] == "too_many_messages" and last["history"] == []


def test_logging_is_off_when_the_environment_was_never_set(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    settings = Settings(_env_file=None, jwt_secret_key="x" * 48, db_password="y" * 24)
    assert settings.chat_logging is False


def test_old_log_files_are_deleted_and_other_files_are_kept(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    (tmp_path / f"{old}.jsonl").write_text("{}\n")
    (tmp_path / "notes.txt").write_text("keep")
    (tmp_path / "backup.jsonl").write_text("keep")
    write_trace(ChatTrace(message="hi"), tmp_path, retention_days=14)
    assert not (tmp_path / f"{old}.jsonl").exists()
    assert (tmp_path / "notes.txt").exists() and (tmp_path / "backup.jsonl").exists()


@pytest.mark.parametrize(("environment", "enabled"), [("development", True), ("production", False)])
def test_logging_defaults_to_on_only_outside_production(environment, enabled):
    settings = Settings(_env_file=None, environment=environment, jwt_secret_key="x" * 48, db_password="y" * 24)
    assert settings.chat_logging is enabled
