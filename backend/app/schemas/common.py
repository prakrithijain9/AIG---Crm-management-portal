"""Shared building blocks for request/response schemas.

The frontend uses camelCase JSON (companyId, jobTitle); Python and the database use
snake_case (company_id, job_title). An alias generator maps between the two, so each
field is declared once in snake_case.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints, model_validator
from pydantic.alias_generators import to_camel


def text_field(max_length: int):
    """Required text: surrounding whitespace removed, then 1..max_length characters."""
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)]


# Exact decimal in Python/DB, sent to the frontend as a JSON number (its type is `number`).
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=14, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]


class InputModel(BaseModel):
    """Request bodies: camelCase keys only, unknown keys rejected (catches typos)."""

    model_config = ConfigDict(alias_generator=to_camel, validate_by_alias=True, validate_by_name=False, extra="forbid")


class UpdateModel(InputModel):
    """PATCH bodies: every field optional, but an explicit null is only allowed where listed."""

    NULLABLE_FIELDS: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_nulls(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None and name not in self.NULLABLE_FIELDS:
                raise ValueError(f"{to_camel(name)} cannot be null")
        return self

    def changes(self) -> dict:
        """Only the fields the client actually sent, keyed by snake_case attribute name."""
        return self.model_dump(exclude_unset=True)


class OutputModel(BaseModel):
    """Response bodies: read from ORM objects, serialised with camelCase keys."""

    model_config = ConfigDict(
        alias_generator=to_camel, from_attributes=True, validate_by_name=True, serialize_by_alias=True
    )

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
