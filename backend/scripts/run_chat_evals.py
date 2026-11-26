"""Live accuracy evals for the CRM assistant. Calls the real LLM; run by hand, never in CI.

    .venv\\Scripts\\python scripts\\run_chat_evals.py                    # all cases, CHAT_MODEL
    .venv\\Scripts\\python scripts\\run_chat_evals.py --model openai/gpt-oss-20b --only overdue

Needs a dev database seeded with demo data (scripts/seed_demo_data.py --apply) and
GROQ_API_KEY in backend/.env. Every case runs in a transaction that is rolled back, so
setup rows never persist.

Expected values are SQL queries run against the same database at the same "today", not
hand-typed numbers, so the cases stay correct as dates move. Checks per case:
  - expected tools were called (``a|b`` = either), forbidden tools were not
  - every expected number/text appears in the reply
  - every number in the reply appears in a tool output, a tool argument, the question or
    the history (the hallucination check; markdown list ordinals are ignored)
  - proposals and navigation hrefs match
"""

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import openai
import yaml
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chat.agent import ChatBusy, ChatFailed, run_chat  # noqa: E402
from app.chat.chatlog import ChatTrace, write_trace  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Activity, Company, Contact  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "evals" / "chat_cases.yaml"
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
MODELS = {"company": Company, "contact": Contact, "activity": Activity}
# Compare text after folding typographic variants models like to emit.
FOLD = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "’": "'", "‘": "'", " ": " ", " ": " "})


def fold(value: str) -> str:
    return value.translate(FOLD).casefold()


class Recorder:
    """Wraps the LLM client and keeps every request and tool call for checking."""

    def __init__(self, client: Any):
        self._client = client
        self.requests: list[dict] = []
        self.calls: list[tuple[str, dict]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        response = self._client.chat.completions.create(**kwargs)
        for call in response.choices[0].message.tool_calls or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            self.calls.append((call.function.name, args))
        return response

    def tool_outputs(self) -> list[str]:
        if not self.requests:
            return []
        return [m["content"] for m in self.requests[-1]["messages"] if m.get("role") == "tool"]


def numbers(textual: str) -> set[Decimal]:
    found = set()
    for raw in NUMBER.findall(textual):
        try:
            found.add(Decimal(raw.replace(",", "").rstrip(".")).normalize())
        except InvalidOperation:
            pass
    return found


def list_lengths(value: Any) -> set[Decimal]:
    """A model may say "3 matches" after counting a short list it was given; allow that."""
    out: set[Decimal] = set()
    if isinstance(value, list):
        out.add(Decimal(len(value)))
        for item in value:
            out |= list_lengths(item)
    elif isinstance(value, dict):
        for item in value.values():
            out |= list_lengths(item)
    return out


def resolve(db, value: Any, today: date) -> Any:
    """Turn {sql: ...} / {today_plus: n} placeholders into real values."""
    if isinstance(value, dict) and "sql" in value:
        rows = db.execute(text(value["sql"]), {"today": today}).scalars().all()
        return rows[0] if len(rows) == 1 else rows
    if isinstance(value, dict) and "today_plus" in value:
        return (today + timedelta(days=value["today_plus"])).isoformat()
    if isinstance(value, dict):
        return {k: resolve(db, v, today) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(db, v, today) for v in value]
    return value


def setup(db, rows: list[dict]) -> None:
    for row in rows:
        ((entity, fields),) = row.items()
        fields = dict(fields)
        for key in ("company", "contact"):
            if key in fields:  # name -> id
                model = MODELS[key]
                fields[f"{key}_id"] = db.query(model).filter(model.name == fields.pop(key)).one().id
        db.add(MODELS[entity](**fields))
    db.flush()


def same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().casefold() == actual.strip().casefold()
    if isinstance(expected, (int, float, Decimal)) or isinstance(actual, (int, float, Decimal)):
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    return str(expected) == str(actual)


def check(case: dict, db, today: date, rec: Recorder, result) -> list[str]:
    problems: list[str] = []
    reply = result.reply
    folded = fold(reply)
    called = [name for name, _ in rec.calls]

    for want in case.get("tools", []):
        if not any(option in called for option in want.split("|")):
            problems.append(f"tool {want} not called (called: {called})")
    for name in case.get("forbid_tools", []):
        if name in called:
            problems.append(f"forbidden tool {name} was called")
    if case.get("no_tools") and called:
        problems.append(f"expected no tools, called {called}")

    reply_nums = numbers(LIST_MARKER.sub("", reply))
    for query in case.get("expect_numbers", []):
        value = resolve(db, {"sql": query}, today)
        for v in value if isinstance(value, list) else [value]:
            if Decimal(str(v)).normalize() not in reply_nums:
                problems.append(f"expected number {v} not in reply")
    for want in resolve(db, case.get("expect_text", []), today):
        for w in want if isinstance(want, list) else [want]:
            if fold(str(w)) not in folded:
                problems.append(f"expected text {w!r} not in reply")
    if any_of := case.get("expect_any_text"):
        if not any(fold(w) in folded for w in any_of):
            problems.append(f"reply has none of {any_of}")
    for bad in case.get("forbid_text", []):
        if fold(bad) in folded:
            problems.append(f"reply contains forbidden text {bad!r}")
    if case.get("expect_question") and "?" not in reply:
        problems.append("expected a clarifying question")

    # Hallucination check: every number in the reply must come from somewhere real.
    grounded: set[Decimal] = numbers(case["ask"])
    for item in case.get("history", []):
        grounded |= numbers(item["content"])
    for out in rec.tool_outputs():
        grounded |= numbers(out)
        try:
            grounded |= list_lengths(json.loads(out))
        except json.JSONDecodeError:
            pass
    for _, args in rec.calls:
        grounded |= numbers(json.dumps(args))
    grounded |= numbers(f"{today.isoformat()} {today.day} {today.year}")
    if stray := sorted(reply_nums - grounded):
        problems.append(f"ungrounded numbers in reply: {[str(n) for n in stray]}")

    want = case.get("expect_proposal")
    if want is None and case.get("expect_no_proposal") and result.proposals:
        problems.append(f"unexpected proposal: {[p['summary'] for p in result.proposals]}")
    if want is not None:
        want = resolve(db, want, today)
        hits = [p for p in result.proposals if p["op"] == want["op"] and p["entity"] == want["entity"]]
        if not hits:
            problems.append(
                f"no {want['op']} {want['entity']} proposal (got {[p['summary'] for p in result.proposals]})"
            )
        else:
            proposal = hits[0]
            if "id" in want and not same(want["id"], proposal.get("id")):
                problems.append(f"proposal id {proposal.get('id')} != {want['id']}")
            for key, value in want.get("input", {}).items():
                if not same(value, proposal["input"].get(key)):
                    problems.append(f"proposal input {key}={proposal['input'].get(key)!r}, expected {value!r}")

    for part in resolve(db, case.get("expect_href", []), today):
        if not any(str(part) in action["href"] for action in result.actions):
            problems.append(f"no action href containing {part!r} (got {[a['href'] for a in result.actions]})")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="append", help="repeatable; default CHAT_MODEL")
    parser.add_argument("--only", help="run case ids containing this text")
    parser.add_argument("--cases", type=Path, default=CASES, help="YAML file of cases")
    parser.add_argument("--pause", type=float, default=6.0, help="seconds between cases (free-tier TPM)")
    parser.add_argument("--verbose", action="store_true", help="print every reply")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252

    settings = get_settings()
    cases = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if args.only in c["id"]]
    today = datetime.now(ZoneInfo(settings.chat_timezone)).date()
    run_id = datetime.now().strftime("%H%M%S")
    # More retries than the app: evals should wait out the per-minute limit, not fail on it.
    def client_for(provider: str):
        if provider == "gemini":
            if settings.gemini_api_key is None:
                raise SystemExit("GEMINI_API_KEY is not set in backend/.env")
            key, base = settings.gemini_api_key, settings.gemini_base_url
        else:
            if settings.groq_api_key is None:
                raise SystemExit("GROQ_API_KEY is not set in backend/.env")
            key, base = settings.groq_api_key, settings.chat_base_url
        return openai.OpenAI(api_key=key.get_secret_value(), base_url=base, timeout=60, max_retries=6)

    clients: dict[str, Any] = {}

    summary = []
    for spec in args.model or [settings.chat_model]:
        # "provider:model" (e.g. gemini:gemini-2.5-flash); bare names are Groq unless they start with "gemini".
        if spec.split(":", 1)[0] in ("groq", "gemini"):
            provider, model = spec.split(":", 1)
        else:
            provider, model = ("gemini" if spec.startswith("gemini") else "groq"), spec
        model_settings = settings.model_copy(update={"chat_model": model})
        if provider not in clients:
            clients[provider] = client_for(provider)
        client = clients[provider]
        passed = errored = 0
        print(f"\n### {model}  ({len(cases)} cases, today={today})", flush=True)
        for case in cases:
            db = SessionLocal()
            rec = Recorder(client)
            started = time.monotonic()
            history = case.get("history", [])
            trace = ChatTrace(case["ask"], history, f"eval-{run_id}-{case['id']}", source="eval")
            try:
                setup(db, resolve(db, case.get("setup", []), today))
                result = run_chat(rec, model_settings, db, case["ask"], history, today, trace=trace)
                problems = check(case, db, today, rec, result)
                trace.set(evalCase=case["id"], evalProblems=problems)
            except (ChatBusy, ChatFailed) as exc:
                errored += 1
                print(f"  ERROR {case['id']}: {type(exc).__name__} (provider)", flush=True)
                time.sleep(args.pause)
                continue
            except Exception as exc:  # a broken case must not stop the run
                problems = [f"harness error: {type(exc).__name__}: {str(exc).splitlines()[0]}"]
                result = SimpleNamespace(reply="")
                trace.set(evalProblems=problems)
            finally:
                db.rollback()
                db.close()
                if settings.chat_logging:
                    trace.data.setdefault("evalCase", case["id"])
                    write_trace(trace, settings.chat_log_path, settings.chat_log_retention_days)
            took = time.monotonic() - started
            if problems:
                print(f"  FAIL  {case['id']} ({took:.1f}s, calls={[n for n, _ in rec.calls]})")
                for problem in problems:
                    print(f"          - {problem}")
                print("          reply: " + result.reply.replace("\n", " ")[:500], flush=True)
            else:
                passed += 1
                print(f"  pass  {case['id']} ({took:.1f}s)", flush=True)
                if args.verbose:
                    print("          reply: " + result.reply.replace("\n", " ")[:500], flush=True)
            time.sleep(args.pause)
        ran = len(cases) - errored
        summary.append((model, passed, ran, errored, 100 * passed / ran if ran else 0.0))

    print("\n## Summary")
    for model, passed, ran, errored, rate in summary:
        print(f"  {model}: {passed}/{ran} passed ({rate:.0f}%), {errored} provider errors")
    return 0 if all(rate >= 95 for *_, rate in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
