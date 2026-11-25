"""Discover users with access to the selected workspaces."""

from typing import Dict, Iterable, List, Mapping, Set, Tuple

from slcli.migration.users.client import AuthMapping, User, Policy
from slcli.migration.users.models import UserToMigrate
from slcli.migration.workspaces import MappedWorkspace, WorkspaceMapping


def discover_user_candidates(
    users: Iterable[User],
    policies: Iterable[Policy],
    mapping: WorkspaceMapping,
    auth_mappings: Iterable[AuthMapping] = (),
) -> List[UserToMigrate]:
    """Find in-scope source users, excluding special users with a '-' email."""
    workspaces_by_source_id = {workspace.source_id: workspace for workspace in mapping.workspaces}
    user_to_auth_mapped_workspaces = _get_auth_mapped_workspaces_by_user(
        auth_mappings, workspaces_by_source_id
    )

    iterated_policies = tuple(policies)
    super_user_policy = [p for p in iterated_policies if _is_superuser_policy(p)]
    if len(super_user_policy) != 1:
        raise ValueError(
            "Expected exactly one super user policy, found {}".format(len(super_user_policy))
        )
    super_user_policy_id = super_user_policy[0].id
    policy_to_workspace_map = _map_policies_to_in_scope_workspaces(
        iterated_policies, workspaces_by_source_id
    )
    candidates = []
    for user in (
        u for u in users if u.type.casefold() == "user" and (u.email or "").strip() != "-"
    ):
        authorized_workspaces = set(user_to_auth_mapped_workspaces.get(user.id, ()))
        authorized_workspaces.update(
            _get_workspaces_for_user_policies(
                user, super_user_policy_id, policy_to_workspace_map, tuple(mapping.workspaces)
            )
        )
        if authorized_workspaces:
            workspaces = tuple(
                workspace for workspace in mapping.workspaces if workspace in authorized_workspaces
            )
            candidates.append(UserToMigrate(user=user, workspaces=workspaces))

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.user.last_name or "",
            candidate.user.first_name or "",
            candidate.user.email or "",
            candidate.user.id,
        ),
    )


def _get_auth_mapped_workspaces_by_user(
    auth_mappings: Iterable[AuthMapping],
    workspaces_in_scope_map: Mapping[str, MappedWorkspace],
) -> Dict[str, Set[MappedWorkspace]]:
    workspaces_by_user: Dict[str, Set[MappedWorkspace]] = {}
    for auth_mapping in auth_mappings:
        if is_workspace_auth_mapping(auth_mapping, workspaces_in_scope_map):
            assert auth_mapping.workspace is not None
            workspaces_by_user.setdefault(auth_mapping.selector.value, set()).add(
                workspaces_in_scope_map[auth_mapping.workspace]
            )
    return workspaces_by_user


def is_workspace_auth_mapping(
    auth_mapping: AuthMapping, workspaces_in_scope_map: Mapping[str, MappedWorkspace] | None = None
) -> bool:
    """Return whether the mapping grants a user access to an in-scope workspace."""
    return (
        auth_mapping.type == "user-id"
        and auth_mapping.selector.key == "user-id"
        and auth_mapping.workspace is not None
        and (workspaces_in_scope_map is None or auth_mapping.workspace in workspaces_in_scope_map)
    )


def _is_superuser_policy(policy: Policy) -> bool:
    return policy.built_in and policy.name.casefold() == "super user"


def _map_policies_to_in_scope_workspaces(
    policies: Iterable[Policy], workspaces_in_scope_map: Mapping[str, MappedWorkspace]
) -> Dict[str, str]:
    policy_to_workspace_map: Dict[str, str] = {}
    for policy in policies:
        if _is_policy_for_in_scope_workspace(policy, workspaces_in_scope_map):
            assert policy.workspace is not None
            policy_to_workspace_map[policy.id] = policy.workspace
    return policy_to_workspace_map


def _is_policy_for_in_scope_workspace(
    policy: Policy, workspaces_in_scope_map: Mapping[str, MappedWorkspace]
) -> bool:
    return (
        bool(policy.template_id)
        and policy.workspace is not None
        and policy.workspace in workspaces_in_scope_map
    )


def _get_workspaces_for_user_policies(
    user: User,
    super_user_policy_id: str,
    policy_to_workspace_map: Dict[str, str],
    in_scope_workspaces: Tuple[MappedWorkspace, ...],
) -> Tuple[MappedWorkspace, ...]:
    if super_user_policy_id in user.policies:
        return in_scope_workspaces
    else:
        workspace_ids = _workspaces_of_policies(user.policies, policy_to_workspace_map)
        return tuple(w for w in in_scope_workspaces if w.source_id in workspace_ids)


def _workspaces_of_policies(
    policies: Iterable[str], policy_to_workspace_map: Mapping[str, str]
) -> List[str]:
    return [
        workspace_id
        for workspace_id in (policy_to_workspace_map.get(policy_id) for policy_id in policies)
        if workspace_id is not None
    ]
