"""The chat log: one JSON line per question, in <CHAT_LOG_DIR>/<date>.jsonl.

It records the question, history, every model call (model, time, tokens, tools requested),
every tool call (arguments, result, SQL run) and the replies. That is CRM data in plain
text, so it is off by default in production and old files are deleted automatically.
Strings shaped like API keys are masked. The app never hands its passwords or session
tokens to this module, but whatever an admin types into the chat is stored as typed.
"""

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Matched against the JSON text, where a newline or tab before a key is the two characters \n or \t.
SECRETS = re.compile(r"(?:(?<![A-Za-z0-9])|(?<=\\[nrt]))(?:gsk_|sk-|AIza)[A-Za-z0-9_\-]{16,}")
DAY_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.jsonl")
_write_lock = threading.Lock()
# Where the SQL listener puts statements: set only while a tool is running in this context.
_sql_sink: ContextVar[list[dict] | None] = ContextVar("chat_sql_sink", default=None)


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


@event.listens_for(Engine, "before_cursor_execute")
def _before_sql(conn, cursor, statement, parameters, context, executemany) -> None:
    if _sql_sink.get() is not None:
        context._chat_log_started = time.perf_counter()


@event.listens_for(Engine, "after_cursor_execute")
def _after_sql(conn, cursor, statement, parameters, context, executemany) -> None:
    sink = _sql_sink.get()
    if sink is not None:
        started = getattr(context, "_chat_log_started", time.perf_counter())
        sink.append({"sql": " ".join(statement.split()), "params": parameters, "ms": _ms(started)})


@event.listens_for(Engine, "handle_error")
def _failed_sql(context) -> None:
    sink = _sql_sink.get()
    if sink is not None and context.statement is not None:  # after_cursor_execute never fires for these
        error = context.original_exception
        sink.append(
            {
                "sql": " ".join(context.statement.split()),
                "params": context.parameters,
                "error": f"{type(context.sqlalchemy_exception or error).__name__}: {str(error)[:300]}",
            }
        )


class ChatTrace:
    """Everything that happens while answering one question. Collecting is cheap; writing is optional."""

    def __init__(
        self,
        message: str,
        history: list[dict] | None = None,
        conversation_id: str | None = None,
        admin_id: str | None = None,
        source: str = "app",
    ):
        self._started = time.perf_counter()
        self.data: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "source": source,
            "conversationId": conversation_id,
            "adminId": admin_id,
            "message": message,
            "history": history or [],
            "status": "error",  # replaced once the request ends properly
            "events": [],
        }

    def set(self, **fields: Any) -> None:
        self.data.update(fields)

    def model_call(self, label: str, started: float, response: Any = None, error: Exception | None = None) -> None:
        entry: dict[str, Any] = {"type": "model", "model": label, "ms": _ms(started)}
        if error is not None:
            status = getattr(error, "status_code", None)
            entry["error"] = f"{type(error).__name__} {status or ''}: {str(error)[:300]}"
        else:
            message = response.choices[0].message
            entry["content"] = message.content
            entry["toolCalls"] = [
                {"name": c.function.name, "arguments": c.function.arguments} for c in message.tool_calls or []
            ]
            usage = getattr(response, "usage", None)
            if usage is not None:
                entry["tokens"] = {
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                    "total": usage.total_tokens,
                }
        self.data["events"].append(entry)

    def run_tool(self, name: str, arguments: str | None, run: Callable[[], dict]) -> dict:
        """Run one tool through ``run()``, recording its arguments, result, time and SQL."""
        queries: list[dict] = []
        token = _sql_sink.set(queries)
        started = time.perf_counter()
        entry: dict[str, Any] = {"type": "tool", "name": name, "arguments": arguments, "sql": queries}
        self.data["events"].append(entry)
        try:
            output = run()
            entry["result"] = {k: v for k, v in output.items() if k != "sources"}
            return output
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            raise
        finally:
            entry["ms"] = _ms(started)
            _sql_sink.reset(token)

    def finish(self) -> dict:
        self.data["durationMs"] = _ms(self._started)
        return self.data


def _delete_old(directory: Path, retention_days: int) -> None:
    oldest = (date.today() - timedelta(days=retention_days)).isoformat()
    for path in directory.glob("*.jsonl"):
        if DAY_FILE.fullmatch(path.name) and path.stem < oldest:
            path.unlink(missing_ok=True)


def read_entries(path: Path) -> tuple[list[dict], int]:
    """The entries in one day's file, and how many lines could not be read."""
    entries, unreadable = [], 0
    # Not splitlines(): it also splits on U+2028 and friends, which can sit inside a message.
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            unreadable += 1
    return entries, unreadable


def write_trace(trace: ChatTrace, directory: Path, retention_days: int) -> None:
    """Append the trace to today's file. A logging problem is reported, never raised."""
    try:
        line = SECRETS.sub("[key removed]", json.dumps(trace.finish(), default=str, ensure_ascii=False))
        with _write_lock:
            directory.mkdir(parents=True, exist_ok=True)
            _delete_old(directory, retention_days)
            with (directory / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception as exc:  # the answer matters more than the log
        logger.warning("Could not write the chat log: %s", type(exc).__name__)
