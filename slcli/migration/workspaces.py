"""Map source workspaces to existing destination workspaces."""

from typing import Iterable, List, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from slcli.migration.workspace_client import Workspace


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

    def workspace(self, source_name: str) -> MappedWorkspace:
        """Return the mapping for a source workspace name.

        Raises:
            KeyError: If the source workspace is not mapped.
        """
        for workspace in self.workspaces:
            if workspace.source_name == source_name:
                return workspace
        raise KeyError(f"Workspace '{source_name}' is not mapped")


class WorkspaceMappingError(ValueError):
    """Requested workspaces that do not exist on the source or destination."""

    def __init__(self, missing_source: List[str], missing_destination: List[str]) -> None:
        """Record the missing workspaces on each side."""
        self.missing_source = missing_source
        self.missing_destination = missing_destination
        problems = []
        if missing_source:
            problems.append(f"unknown source workspace: {', '.join(missing_source)}")
        if missing_destination:
            problems.append(f"missing destination workspace: {', '.join(missing_destination)}")
        super().__init__("; ".join(problems))


def map_workspaces(
    source: Iterable[Workspace],
    destination: Iterable[Workspace],
    requested: Optional[Mapping[str, str]],
) -> WorkspaceMapping:
    """Map requested source workspaces to existing destination workspaces by name.

    Destination workspaces are never created. Every source workspace maps to the
    same-named destination workspace when ``requested`` is None.

    Args:
        source: Every accessible source workspace.
        destination: Every accessible destination workspace.
        requested: Source to destination workspace names; all by name when None.

    Raises:
        WorkspaceMappingError: If any requested workspace is missing on either side.
    """
    source_ids = {workspace.name: workspace.id for workspace in source}
    destination_ids = {workspace.name: workspace.id for workspace in destination}
    pairs = dict(requested) if requested is not None else {name: name for name in source_ids}
    missing_source = sorted(set(pairs).difference(source_ids))
    missing_destination = sorted(
        f"{source_name} -> {destination_name}"
        for source_name, destination_name in pairs.items()
        if destination_name not in destination_ids
    )
    if missing_source or missing_destination:
        raise WorkspaceMappingError(missing_source, missing_destination)
    return WorkspaceMapping(
        workspaces=tuple(
            MappedWorkspace(
                source_name=source_name,
                source_id=source_ids[source_name],
                destination_name=destination_name,
                destination_id=destination_ids[destination_name],
            )
            for source_name, destination_name in sorted(pairs.items())
        )
    )
