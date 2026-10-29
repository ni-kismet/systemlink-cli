"""Shared conventions for typed SystemLink API models used by migration."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

REQUEST_TIMEOUT_SECONDS = 30


class ApiModel(BaseModel):
    """Immutable view of a camelCase API payload that ignores unused fields."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)
