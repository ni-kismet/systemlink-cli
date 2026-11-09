"""Discover source workspaces and synchronize them to destination workspaces."""

from typing import Callable, Iterable, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from slcli.migration.workspace_client import Workspace, WorkspaceClient


class DiscoveredWorkspaces(BaseModel):
    """Every accessible enabled source workspace and the names in scope of a migration."""

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
    """Requested workspaces that are missing or have disabled destinations."""

    def __init__(
        self,
        missing_source: Sequence[str] = (),
        missing_destination: Sequence[str] = (),
        disabled_destination: Sequence[str] = (),
    ) -> None:
        """Record missing source or destination workspaces and disabled destinations."""
        self.missing_source = list(missing_source)
        self.missing_destination = list(missing_destination)
        self.disabled_destination = list(disabled_destination)
        problems = []
        if missing_source:
            problems.append(f"unknown source workspace: {', '.join(missing_source)}")
        if missing_destination:
            problems.append(f"missing destination workspace: {', '.join(missing_destination)}")
        if disabled_destination:
            problems.append(f"disabled destination workspace: {', '.join(disabled_destination)}")
        super().__init__("; ".join(problems))


def discover_workspaces(
    workspace_iterable: Iterable[Workspace], workspaces_names_subset: Optional[Iterable[str]]
) -> DiscoveredWorkspaces:
    """Select enabled source workspaces in scope of a migration.

    Args:
        workspace_iterable: Every accessible source workspace.
        workspaces_names_subset: Source names to migrate; all enabled workspaces when None.

    Raises:
        WorkspaceMappingError: If a requested source workspace is missing or disabled.
    """
    all_workspaces = tuple(
        sorted(
            (workspace for workspace in workspace_iterable if workspace.enabled),
            key=lambda workspace: workspace.name,
        )
    )
    all_workspace_names = [workspace.name for workspace in all_workspaces]
    names_to_include = (
        sorted(workspaces_names_subset)
        if workspaces_names_subset is not None
        else all_workspace_names
    )
    missing = sorted(set(names_to_include).difference(all_workspace_names))
    if missing:
        raise WorkspaceMappingError(missing_source=missing)
    return DiscoveredWorkspaces(source=all_workspaces, selected=tuple(names_to_include))


def synchronize_workspaces(
    source_workspaces: DiscoveredWorkspaces,
    destination_workspaces: Iterable[Workspace],
    create_destination_workspace: Callable[[str], Workspace],
    provided_name_mappings: Optional[Mapping[str, str]],
) -> WorkspaceMapping:
    """Map discovered source workspaces to existing destination workspaces.

    Every selected source workspace maps to the same-named destination workspace
    unless ``provided_name_mappings`` renames it.

    Args:
        source_workspaces: Source workspaces discovered.
        destination_client: Client for running workspace commands on the destination.
        provided_name_mappings: Explicit source-to-destination name mappings;
            when None, destination names match source.

    Raises:
        WorkspaceMappingError: If a mapped destination workspace is disabled.
    """
    destination_workspaces_by_name = {
        workspace.name: workspace for workspace in destination_workspaces
    }

    name_mappings = {
        source_name: (provided_name_mappings or {}).get(source_name, source_name)
        for source_name in source_workspaces.selected
    }
    needed_names = set(name_mappings.values())
    existing_names = set(destination_workspaces_by_name)
    disabled_names = sorted(
        name
        for name in needed_names & existing_names
        if not destination_workspaces_by_name[name].enabled
    )
    if disabled_names:
        raise WorkspaceMappingError(disabled_destination=disabled_names)
    for missing_name in sorted(needed_names - existing_names):
        destination_workspaces_by_name[missing_name] = create_destination_workspace(missing_name)

    source_ids = {workspace.name: workspace.id for workspace in source_workspaces.source}
    return WorkspaceMapping(
        workspaces=tuple(
            MappedWorkspace(
                source_name=source_name,
                source_id=source_ids[source_name],
                destination_name=name_mappings[source_name],
                destination_id=destination_workspaces_by_name[name_mappings[source_name]].id,
            )
            for source_name in source_workspaces.selected
        )
    )
