"""The tool-calling loop: LLM <-> tools, with a hard cap on rounds.

The LLM client is any object with ``chat.completions.create`` (the OpenAI SDK pointed at
Groq in production, a scripted fake in tests). Nothing here logs message text or tool
results: they contain CRM data.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import openai
from sqlalchemy.orm import Session

from app.chat.prompt import build_system_prompt
from app.chat.tools import run_tool, tool_specs
from app.core.config import Settings

logger = logging.getLogger(__name__)

MAX_SOURCES = 10
MAX_CALLS_PER_ROUND = 8
GAVE_UP = "I couldn't complete that — try rephrasing."
# Models like U+2011 (non-breaking hyphen); a name copied from the reply must still match in search.
HYPHENS = str.maketrans(dict.fromkeys(map(chr, range(0x2010, 0x2014)), "-"))  # U+2010..U+2013


class ChatBusy(Exception):
    """The LLM provider is rate limiting us."""


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


def run_chat(
    client: Any,
    settings: Settings,
    db: Session,
    message: str,
    history: list[dict],
    today: date,
) -> ChatResult:
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(today, settings.chat_timezone)},
        *({"role": h["role"], "content": h["content"]} for h in history),
        {"role": "user", "content": message},
    ]
    specs = tool_specs()
    result = ChatResult(reply="")
    seen: set[tuple[str, str]] = set()

    for _ in range(settings.chat_max_tool_rounds):
        try:
            response = client.chat.completions.create(
                model=settings.chat_model,
                messages=messages,
                tools=specs,
                tool_choice="auto",
                temperature=0,
            )
        except openai.RateLimitError:
            raise ChatBusy from None
        except openai.OpenAIError as exc:
            # Type only: the message can echo request content.
            logger.warning("LLM call failed: %s", type(exc).__name__)
            raise ChatFailed from None

        reply = response.choices[0].message
        if not reply.tool_calls:
            result.reply = (reply.content or "").translate(HYPHENS).strip() or GAVE_UP
            return result

        messages.append(_assistant_message(reply))
        for call in reply.tool_calls[:MAX_CALLS_PER_ROUND]:
            output = run_tool(db, call.function.name, call.function.arguments, today)
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
