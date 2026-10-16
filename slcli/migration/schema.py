"""Single schema version for everything migration persists."""

from pydantic import BaseModel, field_validator

SCHEMA_VERSION = 1


class VersionedModel(BaseModel):
    """A persisted model that only loads data written with the current schema."""

    schema_version: int = SCHEMA_VERSION

    @field_validator("schema_version")
    @classmethod
    def _require_current(cls, value: int) -> int:
        if value != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version {value}; expected {SCHEMA_VERSION}")
        return value
