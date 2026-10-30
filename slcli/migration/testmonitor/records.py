"""Pass-through models of Test Monitor records for migration.

Each model declares only the fields migration reads or rewrites. Every other
field is kept exactly as the source returned it and is written to the
destination unchanged, except server-owned fields, which the destination
assigns itself.
"""

from typing import ClassVar, Dict, FrozenSet, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from slcli.migration.testmonitor.writer import Record


class TestMonitorRecord(BaseModel):
    """A Test Monitor record that round-trips every field it does not declare."""

    __test__ = False
    model_config = ConfigDict(
        extra="allow", frozen=True, alias_generator=to_camel, populate_by_name=True
    )

    server_owned: ClassVar[FrozenSet[str]] = frozenset()
    properties: Dict[str, str] = Field(default_factory=dict)

    @field_validator("properties", mode="before")
    @classmethod
    def _drop_null_properties(cls, value: Optional[Dict[str, Optional[str]]]) -> Dict[str, str]:
        # SystemLink Server returns null property values, which its API model does
        # not allow and destinations reject.
        return {key: item for key, item in (value or {}).items() if item is not None}

    @property
    def key(self) -> str:
        """Return the ID that identifies this record within its collection."""
        raise NotImplementedError

    def create_request(self, overrides: Record) -> Record:
        """Return this record as a create request, with ``overrides`` replacing fields."""
        fields = self.model_dump(by_alias=True, exclude_unset=True, exclude=set(self.server_owned))
        return {**fields, **overrides}


class Product(TestMonitorRecord):
    """A product, identified on every server by its part number."""

    server_owned: ClassVar[FrozenSet[str]] = frozenset({"id", "updatedAt", "fileIds"})
    id: str
    part_number: str
    workspace: Optional[str] = None

    @property
    def key(self) -> str:
        """Return the product ID."""
        return self.id


class Result(TestMonitorRecord):
    """A test result. File and data table references are not migrated yet."""

    server_owned: ClassVar[FrozenSet[str]] = frozenset(
        {"id", "updatedAt", "fileIds", "dataTableIds", "statusTypeSummary"}
    )
    id: str

    @property
    def key(self) -> str:
        """Return the result ID."""
        return self.id


class Step(TestMonitorRecord):
    """A step, identified by a step ID that is unique within its result."""

    server_owned: ClassVar[FrozenSet[str]] = frozenset(
        {"path", "path_ids", "updatedAt", "hasChildren", "workspace"}
    )
    step_id: str
    parent_id: str
    path_ids: List[str]

    @property
    def key(self) -> str:
        """Return the step ID."""
        return self.step_id
