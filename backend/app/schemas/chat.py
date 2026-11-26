from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

from app.schemas.common import InputModel

MAX_HISTORY = 12


class HistoryItem(InputModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(max_length=4000)]


class ChatRequest(InputModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    # The server is stateless: the browser sends the last few turns each time.
    history: list[HistoryItem] = Field(default_factory=list, max_length=MAX_HISTORY)
    # Made by the browser so the chat log can group the questions of one conversation.
    conversation_id: Annotated[str, StringConstraints(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")] | None = None


class ChatSource(BaseModel):
    type: Literal["company", "contact", "deal", "activity"]
    id: str
    label: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, serialize_by_alias=True)

    reply: str
    proposals: list[dict]
    actions: list[dict]
    sources: list[ChatSource]
