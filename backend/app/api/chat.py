"""POST /api/chat: the CRM assistant. Mounted behind require_admin (session + CSRF)."""

import logging
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAI

from app.api.auth import AppSettings, CurrentSession, require_admin
from app.api.common import DbSession
from app.chat.agent import ChatBusy, ChatFailed, run_chat
from app.chat.ratelimit import chat_limiter
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


def get_fallback_client(settings: AppSettings) -> OpenAI | None:
    """The same SDK pointed at the fallback provider (Gemini), or None if it has no key. Tests override this."""
    if settings.gemini_api_key is None:
        return None
    return OpenAI(
        api_key=settings.gemini_api_key.get_secret_value(),
        base_url=settings.chat_fallback_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: DbSession,
    settings: AppSettings,
    session: Annotated[CurrentSession, Depends(require_admin)],
    client: Annotated[OpenAI | None, Depends(get_llm_client)],
    fallback: Annotated[OpenAI | None, Depends(get_fallback_client)],
) -> ChatResponse:
    if client is None and fallback is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant is not configured.")
    wait = chat_limiter.check(str(session.admin.id), settings.chat_rate_limit_per_min)
    if wait is not None:
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
            [h.model_dump() for h in payload.history],
            today,
            fallback,
        )
    except ChatBusy:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "The assistant is busy right now. Try again in a minute."
        ) from None
    except ChatFailed:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The assistant could not be reached.") from None
    finally:
        db.rollback()  # reads only; end the transaction so the connection goes back clean
    return ChatResponse(
        reply=result.reply, proposals=result.proposals, actions=result.actions, sources=result.sources
    )
