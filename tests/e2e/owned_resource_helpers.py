"""Ownership marking for resources created by E2E fixtures."""

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Protocol

OWNER_PROPERTY = "slcli.e2e.owner"
"""Property that marks a resource as created and cleaned up by an E2E fixture."""

MIGRATION_DISCOVERY_OWNER = "migration-discovery"


class PropertyResource(Protocol):
    """A resource with an ID and custom string properties."""

    @property
    def id(self) -> str:
        """Return the resource ID."""
        ...

    @property
    def properties(self) -> Mapping[str, str]:
        """Return the resource's custom properties."""
        ...


@dataclass(frozen=True)
class OwnedResourceIds:
    """Resource IDs split by whether they carry the expected owner."""

    owned: List[str]
    unowned: List[str]


def owner_properties(owner: str) -> dict[str, str]:
    """Return the properties that mark a resource as owned by ``owner``."""
    return {OWNER_PROPERTY: owner}


def split_owned_resource_ids(resources: Iterable[PropertyResource], owner: str) -> OwnedResourceIds:
    """Split resource IDs by an exact owner match."""
    owned: List[str] = []
    unowned: List[str] = []
    for resource in resources:
        (owned if resource.properties.get(OWNER_PROPERTY) == owner else unowned).append(resource.id)
    return OwnedResourceIds(owned=owned, unowned=unowned)
