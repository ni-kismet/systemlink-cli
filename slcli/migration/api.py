"""Shared conventions for typed SystemLink API models used by migration."""

from typing import Mapping, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

REQUEST_TIMEOUT_SECONDS = 30

# Headers that may correlate a request with server logs, in order of preference.
CORRELATION_HEADERS = (
    "x-ni-correlation-id",
    "x-correlation-id",
    "x-request-id",
    "request-id",
    "traceparent",
)


def correlation_id(headers: Optional[Mapping[str, str]]) -> Optional[str]:
    """Return the first server correlation header value, if any.

    Args:
        headers: Case-insensitive response headers, such as ``requests.Response.headers``.
    """
    if headers is None:
        return None
    for name in CORRELATION_HEADERS:
        value = headers.get(name)
        if value:
            return value
    return None


class ApiModel(BaseModel):
    """Immutable view of a camelCase API payload that ignores unused fields."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)
