from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class LoginRequest(BaseModel):
    """Sign-in form. Deliberately lenient: a missing, malformed or oversized value is just a
    failed sign-in (401), so validation errors never reflect the submitted password."""

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    username: str = ""
    password: str = ""


class SessionRead(BaseModel):
    """The signed-in admin. csrfToken must be sent back in X-CSRF-Token on writes."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        serialize_by_alias=True,
        hide_input_in_errors=True,  # never put the CSRF token in an error message
    )

    username: str
    csrf_token: str
    expires_at: datetime
