"""POST /api/chat: the CRM assistant. Mounted behind require_admin (session + CSRF)."""

import logging
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAI

from app.api.auth import AppSettings, CurrentSession, require_admin
from app.api.common import DbSession
from app.chat.agent import ChatBusy, ChatFailed, LlmTarget, run_chat
from app.chat.chatlog import ChatTrace, write_trace
from app.chat.ratelimit import chat_limiter
from app.core.config import parse_model_chain
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

LLM_TIMEOUT_SECONDS = 30


def get_llm_client(settings: AppSettings) -> OpenAI | None:
    """The OpenAI SDK pointed at the primary provider (Groq), or None if it has no key. Tests override this."""
    if settings.groq_api_key is None:
        return None
    return OpenAI(
        api_key=settings.groq_api_key.get_secret_value(),
        base_url=settings.chat_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )


def get_fallback_targets(settings: AppSettings) -> list[LlmTarget]:
    """Fallback models in configured order, skipping providers without a key. Tests override this."""
    providers = {
        "groq": (settings.groq_api_key, settings.chat_base_url),
        "gemini": (settings.gemini_api_key, settings.gemini_base_url),
    }
    clients: dict[str, OpenAI] = {}
    targets: list[LlmTarget] = []
    for provider, model in parse_model_chain(settings.chat_fallback_models):
        key, base_url = providers[provider]
        if key is None:
            continue
        if provider not in clients:
            clients[provider] = OpenAI(
                api_key=key.get_secret_value(), base_url=base_url, timeout=LLM_TIMEOUT_SECONDS, max_retries=1
            )
        targets.append(LlmTarget(clients[provider], model, f"{provider}:{model}"))
    return targets


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: DbSession,
    settings: AppSettings,
    session: Annotated[CurrentSession, Depends(require_admin)],
    client: Annotated[OpenAI | None, Depends(get_llm_client)],
    fallbacks: Annotated[list[LlmTarget], Depends(get_fallback_targets)],
) -> ChatResponse:
    if client is None and not fallbacks:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant is not configured.")
    history = [h.model_dump() for h in payload.history]
    trace = ChatTrace(payload.message, history, payload.conversation_id, str(session.admin.id))

    def save_log() -> None:
        if settings.chat_logging:
            write_trace(trace, settings.chat_log_path, settings.chat_log_retention_days)

    wait = chat_limiter.check(str(session.admin.id), settings.chat_rate_limit_per_min)
    if wait is not None:
        trace.set(status="too_many_messages", history=[])  # a looping client must not fill the disk
        save_log()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "You're sending messages too quickly. Wait a moment and try again.",
            headers={"Retry-After": str(int(wait) + 1)},
        )
    today = datetime.now(ZoneInfo(settings.chat_timezone)).date()
    try:
        result = run_chat(
            client,
            settings,
            db,
            payload.message,
            history,
            today,
            fallbacks,
            trace,
        )
    except ChatBusy:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "The assistant is busy right now. Try again in a minute."
        ) from None
    except ChatFailed:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The assistant could not be reached.") from None
    finally:
        db.rollback()  # reads only; end the transaction so the connection goes back clean
        save_log()  # also for failures: those are the entries worth reading
    return ChatResponse(
        reply=result.reply, proposals=result.proposals, actions=result.actions, sources=result.sources
    )
