"""The tool-calling loop: LLM <-> tools, with a hard cap on rounds.

The LLM client is any object with ``chat.completions.create`` (the OpenAI SDK pointed at
Groq in production, a scripted fake in tests). The server log (``logger``) never carries
message text or tool results, because they are CRM data. Those go only to the chat log
(``chatlog.py``), which is off by default in production.
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import openai
from sqlalchemy.orm import Session

from app.chat.chatlog import ChatTrace
from app.chat.prompt import build_system_prompt
from app.chat.tools import run_tool, tool_specs
from app.core.config import Settings

logger = logging.getLogger(__name__)

MAX_SOURCES = 10
MAX_CALLS_PER_ROUND = 8
GAVE_UP = "I couldn't complete that — try rephrasing."
# Models like U+2011 (non-breaking hyphen); a name copied from the reply must still match in search.
HYPHENS = str.maketrans(dict.fromkeys(map(chr, range(0x2010, 0x2014)), "-"))  # U+2010..U+2013
# Sent before the last allowed round, so a model that keeps looking things up still answers.
ANSWER_NOW = "No more tool calls. Answer now from the results above, and say what you could not find."
# Proposals save nothing, so a reply saying the change happened is replaced. The prompt forbids
# it, but models still do it.
NOT_SAVED_YET = "I've prepared this change. Nothing is saved yet: review the card below and confirm it."
_DONE_WORDS = "updated|created|added|deleted|removed|saved|marked|changed|moved|set|logged|completed|scheduled"
CLAIMS_DONE = re.compile(
    rf"\b(?:has|have) (?:now )?been (?:successfully )?(?:{_DONE_WORDS})\b"
    rf"|\bI(?:'ve|’ve| have)? (?:now )?(?:{_DONE_WORDS})\b",
    re.IGNORECASE,
)
# Record ids are for tools. Drop them, with any "ID" label and brackets, from what the user reads.
RECORD_ID = re.compile(
    r"[ \t]*[-–—]?[ \t]*\(?(?:\bID\b:?[ \t]*)?`?\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b`?\)?",
    re.IGNORECASE,
)


def _clean_reply(text: str, has_proposals: bool) -> str:
    text = RECORD_ID.sub("", text.translate(HYPHENS)).strip()
    if has_proposals and CLAIMS_DONE.search(text):
        return NOT_SAVED_YET
    return text or GAVE_UP


class ChatBusy(Exception):
    """The LLM provider is rate limiting us."""

    def __init__(self, retry_after: float | None = None):
        super().__init__()
        self.retry_after = retry_after


class ChatFailed(Exception):
    """The LLM provider could not be reached or errored."""


@dataclass
class ChatResult:
    reply: str
    proposals: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)


def _assistant_message(message: Any) -> dict:
    out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments or "{}"},
            }
            for call in message.tool_calls
        ]
    return out


@dataclass(frozen=True)
class LlmTarget:
    """One model to try: an OpenAI-SDK-compatible client, the model id, and a label for logs."""

    client: Any
    model: str
    label: str


class Cooldowns:
    """Models that just said "rate limited" are skipped until the provider says they are free again.

    Without this, once a model's daily cap is gone every question would first waste a request on it.
    In process memory only, so each uvicorn worker learns separately; that is fine, it is an optimisation.
    """

    DEFAULT_SECONDS = 60.0  # Gemini sends no retry-after
    MIN_SECONDS = 5.0
    MAX_SECONDS = 900.0

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._until: dict[str, float] = {}

    def block(self, label: str, seconds: float | None) -> None:
        wait = self.DEFAULT_SECONDS if seconds is None else seconds
        self._until[label] = self._clock() + min(max(wait, self.MIN_SECONDS), self.MAX_SECONDS)

    def active(self, label: str) -> bool:
        return self._until.get(label, 0.0) > self._clock()

    def reset(self) -> None:
        self._until.clear()


cooldowns = Cooldowns()


def _retry_after(exc: openai.RateLimitError) -> float | None:
    try:
        return float(exc.response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None


def run_chat(
    client: Any | None,
    settings: Settings,
    db: Session,
    message: str,
    history: list[dict],
    today: date,
    fallbacks: list[LlmTarget] | None = None,
    trace: ChatTrace | None = None,
) -> ChatResult:
    """Answer on the primary model; if it is rate limited or down, redo the whole turn on the next one.

    Safe to repeat: tools only read, and proposals write nothing until the user confirms. `client`
    may be None when only fallbacks are configured.
    """
    targets: list[LlmTarget] = []
    if client is not None:
        targets.append(LlmTarget(client, settings.chat_model, f"groq:{settings.chat_model}"))
    targets.extend(fallbacks or [])

    trace = trace or ChatTrace(message, history)  # collected either way; the caller decides to write it
    trace.set(promptVersion=_prompt_version(settings))
    busy = False
    for index, target in enumerate(targets):
        if cooldowns.active(target.label):
            busy = True  # known to be rate limited right now; do not spend a request finding out again
            trace.data["events"].append({"type": "skipped", "model": target.label, "why": "cooling down"})
            continue
        try:
            result = _attempt(target, settings, db, message, history, today, trace)
        except ChatBusy as exc:
            busy = True
            cooldowns.block(target.label, exc.retry_after)
            logger.warning("%s is rate limited", target.label)
            continue
        except ChatFailed:
            logger.warning("%s failed", target.label)
            continue
        if index > 0:
            logger.info("Answered on %s", target.label)
        trace.set(
            status="gave_up" if result.reply == GAVE_UP else "ok",
            answeredBy=target.label,
            reply=result.reply,
            proposals=result.proposals,
            actions=result.actions,
            sources=result.sources,
        )
        return result
    # Every model failed. "Busy" wins: the user should wait and retry, not assume an outage.
    trace.set(status="busy" if busy else "failed")
    raise ChatBusy if busy else ChatFailed


def _prompt_version(settings: Settings) -> str:
    """Changes when the instructions or tool descriptions change, so log entries can be compared."""
    text = build_system_prompt(date(2000, 1, 1), settings.chat_timezone) + json.dumps(tool_specs())
    return hashlib.sha256(text.encode()).hexdigest()[:10]


def _attempt(
    target: LlmTarget,
    settings: Settings,
    db: Session,
    message: str,
    history: list[dict],
    today: date,
    trace: ChatTrace,
) -> ChatResult:
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(today, settings.chat_timezone)},
        *({"role": h["role"], "content": h["content"]} for h in history),
        {"role": "user", "content": message},
    ]
    specs = tool_specs()
    result = ChatResult(reply="")
    seen: set[tuple[str, str]] = set()

    for round_number in range(1, settings.chat_max_tool_rounds + 1):
        if round_number == settings.chat_max_tool_rounds > 1:
            messages.append({"role": "system", "content": ANSWER_NOW})
        started = time.perf_counter()
        try:
            response = target.client.chat.completions.create(
                model=target.model,
                messages=messages,
                tools=specs,
                tool_choice="auto",
                temperature=0,
            )
        except openai.RateLimitError as exc:
            trace.model_call(target.label, started, error=exc)
            raise ChatBusy(_retry_after(exc)) from None
        except openai.OpenAIError as exc:
            trace.model_call(target.label, started, error=exc)
            # Type only: the message can echo request content.
            logger.warning("LLM call failed: %s", type(exc).__name__)
            raise ChatFailed from None

        trace.model_call(target.label, started, response)
        reply = response.choices[0].message
        if not reply.tool_calls:
            trace.set(modelReply=reply.content or "")
            result.reply = _clean_reply(reply.content or "", bool(result.proposals))
            return result

        messages.append(_assistant_message(reply))
        for call in reply.tool_calls[:MAX_CALLS_PER_ROUND]:
            name, arguments = call.function.name, call.function.arguments
            output = trace.run_tool(name, arguments, lambda: run_tool(db, name, arguments, today))
            if "error" in output:
                logger.info("Tool %s returned an error", call.function.name)
            for source in output.pop("sources", []):
                key = (source["type"], source["id"])
                if key not in seen and len(result.sources) < MAX_SOURCES:
                    seen.add(key)
                    result.sources.append(source)
            if "proposalId" in output:
                result.proposals.append(output)
            if "action" in output:
                result.actions.append(output["action"])
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(output, default=str)}
            )
        # Calls beyond the per-round cap still need a reply, or the provider rejects the history.
        for call in reply.tool_calls[MAX_CALLS_PER_ROUND:]:
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps({"error": "Too many tool calls at once."})}
            )

    logger.info("Chat hit the tool round limit (%s)", settings.chat_max_tool_rounds)
    return ChatResult(reply=GAVE_UP, proposals=[], actions=[], sources=[])
