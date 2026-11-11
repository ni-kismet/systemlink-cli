"""Discover source workspaces and synchronize them to destination workspaces."""

from typing import Iterable, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from slcli.migration.workspace_client import Workspace


class DiscoveredWorkspaces(BaseModel):
    """Every accessible source workspace and the names in scope of a migration."""

    model_config = ConfigDict(frozen=True)

    source: Tuple[Workspace, ...] = ()
    selected: Tuple[str, ...] = ()


class MappedWorkspace(BaseModel):
    """One source workspace and the existing destination workspace it migrates to."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    source_id: str
    destination_name: str
    destination_id: str


class WorkspaceMapping(BaseModel):
    """Resolved source-to-destination workspaces, ordered by source name."""

    model_config = ConfigDict(frozen=True)

    workspaces: Tuple[MappedWorkspace, ...] = ()


class WorkspaceMappingError(ValueError):
    """Requested workspaces that do not exist on the source or destination."""

    def __init__(
        self, missing_source: Sequence[str] = (), missing_destination: Sequence[str] = ()
    ) -> None:
        """Record the missing workspaces on each side."""
        self.missing_source = list(missing_source)
        self.missing_destination = list(missing_destination)
        problems = []
        if missing_source:
            problems.append(f"unknown source workspace: {', '.join(missing_source)}")
        if missing_destination:
            problems.append(f"missing destination workspace: {', '.join(missing_destination)}")
        super().__init__("; ".join(problems))


def discover_workspaces(
    source: Iterable[Workspace], requested: Optional[Iterable[str]]
) -> DiscoveredWorkspaces:
    """Select the source workspaces in scope of a migration.

    Args:
        source: Every accessible source workspace.
        requested: Source workspace names to migrate; all workspaces when None.

    Raises:
        WorkspaceMappingError: If a requested workspace does not exist on the source.
    """
    workspaces = tuple(sorted(source, key=lambda workspace: workspace.name))
    names = [workspace.name for workspace in workspaces]
    selected = sorted(requested) if requested is not None else names
    missing = sorted(set(selected).difference(names))
    if missing:
        raise WorkspaceMappingError(missing_source=missing)
    return DiscoveredWorkspaces(source=workspaces, selected=tuple(selected))


def synchronize_workspaces(
    discovered: DiscoveredWorkspaces,
    destination: Iterable[Workspace],
    requested: Optional[Mapping[str, str]],
) -> WorkspaceMapping:
    """Map discovered source workspaces to existing destination workspaces.

    Destination workspaces are not created yet. Every selected source workspace
    maps to the same-named destination workspace unless ``requested`` renames it.

    Args:
        discovered: Source workspaces in scope of the migration.
        destination: Every accessible destination workspace.
        requested: Source to destination workspace names; all by name when None.

    Raises:
        WorkspaceMappingError: If a destination workspace does not exist.
    """
    source_ids = {workspace.name: workspace.id for workspace in discovered.source}
    destination_ids = {workspace.name: workspace.id for workspace in destination}
    pairs = {name: (requested or {}).get(name, name) for name in discovered.selected}
    missing = sorted(
        f"{source_name} -> {destination_name}"
        for source_name, destination_name in pairs.items()
        if destination_name not in destination_ids
    )
    if missing:
        raise WorkspaceMappingError(missing_destination=missing)
    return WorkspaceMapping(
        workspaces=tuple(
            MappedWorkspace(
                source_name=source_name,
                source_id=source_ids[source_name],
                destination_name=destination_name,
                destination_id=destination_ids[destination_name],
            )
            for source_name, destination_name in pairs.items()
        )
    )
