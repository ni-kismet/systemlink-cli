"""Discover and migrate users with workspace access."""

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

import click
import questionary
import requests
from pydantic import Field, field_validator

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.migration.workspaces import MappedWorkspace, WorkspaceMapping

PAGE_SIZE = 100
_logger = logging.getLogger("slcli.migration")


class MigrationUser(ApiModel):
    """A user record returned by User Service."""

    id: str
    type: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    properties: Dict[str, str] = Field(default_factory=dict)
    policies: List[str] = Field(default_factory=list)

    @field_validator("keywords", "policies", mode="before")
    @classmethod
    def _empty_lists(cls, value: Optional[List[str]]) -> List[str]:
        return value or []

    @field_validator("properties", mode="before")
    @classmethod
    def _empty_properties(cls, value: Optional[Dict[str, str]]) -> Dict[str, str]:
        return value or {}


class _UserPage(ApiModel):
    users: List[MigrationUser]
    continuation_token: Optional[str] = None


class _Policy(ApiModel):
    id: str
    name: str
    built_in: bool = False
    template_id: Optional[str] = None
    workspace: Optional[str] = None


class _PolicyPage(ApiModel):
    policies: List[_Policy]


class _AuthMappingSelector(ApiModel):
    key: str
    value: str


class _AuthMapping(ApiModel):
    type: str
    selector: _AuthMappingSelector
    workspace: Optional[str] = None


class _AuthMappingPage(ApiModel):
    auth_mappings: List[_AuthMapping]


class _PolicyTemplate(ApiModel):
    id: str


class _PolicyTemplatePage(ApiModel):
    policy_templates: List[_PolicyTemplate]


class _CreatedUser(ApiModel):
    id: str


@dataclass(frozen=True)
class UserCandidate:
    """A source user and migrated workspaces they will be authorized for."""

    user: MigrationUser
    workspaces: Tuple[MappedWorkspace, ...]


@dataclass(frozen=True)
class _UserMigrationTask:
    """One user record and its missing workspace auth-mappings."""

    source_user: MigrationUser
    email: str
    destination_user_id: Optional[str]
    workspaces: Tuple[MappedWorkspace, ...]


class UserMigrationClient:
    """Profile-bound user, policy, and auth-mapping operations."""

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
        write_session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize the User Service client."""
        self._connection = connection
        self._base_url = connection.base_url.rstrip("/")
        self._session = session or connection.create_session(("niuser/v1/users/query",))
        self._write_session = write_session or connection.create_write_session()

    @property
    def readonly(self) -> bool:
        """Return whether the profile prohibits destination writes."""
        return self._connection.readonly

    def query_users(self, include_inactive: bool = False) -> List[MigrationUser]:
        """Return users across all pages, optionally including non-active accounts."""
        url = f"{self._base_url}/niuser/v1/users/query"
        payload: Dict[str, object] = {"take": PAGE_SIZE}
        if not include_inactive:
            payload["filter"] = 'status = "active"'
        users: List[MigrationUser] = []
        while True:
            response = self._session.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            page = _UserPage.model_validate(response.json())
            users.extend(page.users)
            if not page.continuation_token:
                return users
            payload = {**payload, "continuationToken": page.continuation_token}

    def query_policies(self) -> List[_Policy]:
        """Return every policy, following the authorization service's offset pages."""
        url = f"{self._base_url}/niauth/v1/policies"
        policies: List[_Policy] = []
        skip = 0
        while True:
            response = self._session.get(
                url,
                params={"take": PAGE_SIZE, "skip": skip},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            page = _PolicyPage.model_validate(response.json())
            policies.extend(page.policies)
            if len(page.policies) < PAGE_SIZE:
                return policies
            skip += len(page.policies)

    def query_auth_mappings(self) -> List[_AuthMapping]:
        """Return all user-ID auth-mappings, following offset pages."""
        url = f"{self._base_url}/niuser/v1/auth-mappings"
        mappings: List[_AuthMapping] = []
        skip = 0
        while True:
            params: Dict[str, Union[str, int]] = {
                "type": "user-id",
                "take": PAGE_SIZE,
                "skip": skip,
            }
            response = self._session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            page = _AuthMappingPage.model_validate(response.json())
            mappings.extend(page.auth_mappings)
            if len(page.auth_mappings) < PAGE_SIZE:
                return mappings
            skip += len(page.auth_mappings)

    def collaborator_template_id(self) -> Optional[str]:
        """Return the built-in Collaborator user policy template ID, if available."""
        response = self._session.get(
            f"{self._base_url}/niauth/v1/policy-templates",
            params={"name": "Collaborator", "type": "user", "builtIn": "true"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        page = _PolicyTemplatePage.model_validate(response.json())
        return page.policy_templates[0].id if page.policy_templates else None

    def create_user(self, source_user: MigrationUser, email: str) -> str:
        """Create a user using the email as the default identity-provider ID."""
        self._ensure_writable("create users")
        response = self._write_session.post(
            f"{self._base_url}/niuser/v1/users",
            json={
                "type": "user",
                "firstName": source_user.first_name or "",
                "lastName": source_user.last_name or "",
                "email": email,
                "phone": "",
                "niuaId": email,
                "login": "",
                "policies": [],
                "keywords": source_user.keywords,
                "properties": source_user.properties,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _CreatedUser.model_validate(response.json()).id

    def create_auth_mapping(self, user_id: str, workspace_id: str, template_id: str) -> None:
        """Grant a user the specified policy template in one workspace."""
        self._ensure_writable("create auth-mappings")
        response = self._write_session.post(
            f"{self._base_url}/niuser/v1/auth-mappings",
            json={
                "type": "user-id",
                "selector": {"key": "user-id", "value": user_id},
                "policyTemplateId": template_id,
                "workspace": workspace_id,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    def _ensure_writable(self, operation: str) -> None:
        if self._connection.readonly:
            raise click.ClickException(
                f"Cannot {operation}: profile '{self._connection.profile_name}' is in readonly mode"
            )


def discover_user_candidates(
    users: Iterable[MigrationUser],
    policies: Iterable[_Policy],
    mapping: WorkspaceMapping,
    auth_mappings: Iterable[_AuthMapping] = (),
) -> List[UserCandidate]:
    """Find active source users with workspace memberships in the migration scope."""
    mapped_by_source_id = {workspace.source_id: workspace for workspace in mapping.workspaces}
    workspaces_by_policy: Dict[str, Set[str]] = {}
    workspaces_by_user: Dict[str, Set[str]] = {}
    super_user_policy_ids: Set[str] = set()

    for policy in policies:
        if policy.built_in and policy.name.casefold() == "super user":
            super_user_policy_ids.add(policy.id)
        if (
            policy.template_id
            and policy.workspace is not None
            and policy.workspace in mapped_by_source_id
        ):
            workspaces_by_policy.setdefault(policy.id, set()).add(policy.workspace)

    for auth_mapping in auth_mappings:
        if (
            auth_mapping.type == "user-id"
            and auth_mapping.selector.key == "user-id"
            and auth_mapping.workspace is not None
            and auth_mapping.workspace in mapped_by_source_id
        ):
            workspaces_by_user.setdefault(auth_mapping.selector.value, set()).add(
                auth_mapping.workspace
            )

    candidates: List[UserCandidate] = []
    for user in users:
        if user.type.casefold() != "user":
            continue
        workspace_ids = set(workspaces_by_user.get(user.id, set()))
        for policy_id in user.policies:
            if policy_id in super_user_policy_ids:
                workspace_ids.update(mapped_by_source_id)
            workspace_ids.update(workspaces_by_policy.get(policy_id, set()))
        workspaces = tuple(
            workspace for workspace in mapping.workspaces if workspace.source_id in workspace_ids
        )
        if workspaces:
            candidates.append(UserCandidate(user=user, workspaces=workspaces))
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.user.first_name or "",
            candidate.user.last_name or "",
            candidate.user.email or "",
            candidate.user.id,
        ),
    )


def _candidate_label(candidate: UserCandidate) -> str:
    name = " ".join(part for part in (candidate.user.first_name, candidate.user.last_name) if part)
    email = candidate.user.email or "missing email"
    workspaces = ", ".join(
        (
            f"{workspace.source_name} -> {workspace.destination_name}"
            if workspace.source_name != workspace.destination_name
            else workspace.destination_name
        )
        for workspace in candidate.workspaces
    )
    return f"{name or '(unnamed)'}  {email}  {workspaces}"


def _select_users(candidates: List[UserCandidate]) -> List[UserCandidate]:
    choices = [
        questionary.Choice(_candidate_label(candidate), value=candidate.user.id, checked=True)
        for candidate in candidates
    ]
    selected_ids = questionary.checkbox(
        "Select users to migrate. Missing destination workspace access is granted through "
        "the Collaborator role; uncheck users to omit.",
        choices=choices,
    ).ask()
    if selected_ids is None:
        raise click.Abort()
    selected = set(selected_ids)
    return [candidate for candidate in candidates if candidate.user.id in selected]


def _resolve_emails(candidates: List[UserCandidate]) -> Dict[str, str]:
    emails: Dict[str, str] = {}
    for candidate in candidates:
        email = (candidate.user.email or "").strip()
        if not email:
            entered = click.prompt(
                f"An email is required for authentication but was missing for user "
                f"'{_candidate_label(candidate)}'. Enter it now, or leave blank to skip "
                "migrating this user",
                default="",
                show_default=False,
            )
            email = entered.strip()
            if not email:
                click.echo(f"Skipping user '{_candidate_label(candidate)}' without an email.")
                continue
        emails[candidate.user.id] = email
    return emails


def _plan_user_migrations(
    candidates: List[UserCandidate],
    emails: Dict[str, str],
    existing_users: List[MigrationUser],
    existing_mappings: List[_AuthMapping],
) -> Tuple[List[_UserMigrationTask], List[str]]:
    email_counts = Counter(email.casefold() for email in emails.values())
    destination_users: Dict[str, List[MigrationUser]] = {}
    for user in existing_users:
        if user.email:
            destination_users.setdefault(user.email.strip().casefold(), []).append(user)

    mapped_workspaces: Dict[str, Set[str]] = {}
    for auth_mapping in existing_mappings:
        if (
            auth_mapping.type == "user-id"
            and auth_mapping.selector.key == "user-id"
            and auth_mapping.workspace
        ):
            mapped_workspaces.setdefault(auth_mapping.selector.value, set()).add(
                auth_mapping.workspace
            )

    tasks: List[_UserMigrationTask] = []
    warnings: List[str] = []
    for candidate in candidates:
        email = emails.get(candidate.user.id)
        if email is None:
            continue
        if email_counts[email.casefold()] > 1:
            warnings.append(
                f"Skipping '{_candidate_label(candidate)}': multiple selected source users "
                f"resolve to the same email address."
            )
            continue
        matches = destination_users.get(email.casefold(), [])
        if len(matches) > 1:
            warnings.append(
                f"Skipping '{_candidate_label(candidate)}': multiple destination users match "
                "this email address."
            )
            continue
        destination_user = matches[0] if matches else None
        already_mapped = (
            set(mapped_workspaces.get(destination_user.id, set())) if destination_user else set()
        )
        workspaces: List[MappedWorkspace] = []
        for workspace in candidate.workspaces:
            if workspace.destination_id not in already_mapped:
                workspaces.append(workspace)
                already_mapped.add(workspace.destination_id)
        tasks.append(
            _UserMigrationTask(
                source_user=candidate.user,
                email=email,
                destination_user_id=destination_user.id if destination_user else None,
                workspaces=tuple(workspaces),
            )
        )
    return tasks, warnings


def migrate_users(
    source_profile: str,
    destination_profile: str,
    mapping: WorkspaceMapping,
) -> int:
    """Review eligible source users and migrate their records and workspace access."""
    if not mapping.workspaces:
        click.echo("Successfully migrated 0 users.")
        return 0

    source_client = UserMigrationClient(resolve_migration_connection(source_profile))
    candidates = discover_user_candidates(
        source_client.query_users(),
        source_client.query_policies(),
        mapping,
        source_client.query_auth_mappings(),
    )
    if not candidates:
        click.echo("Successfully migrated 0 users.")
        return 0

    selected = _select_users(candidates)
    emails = _resolve_emails(selected)
    if not emails:
        click.echo("Successfully migrated 0 users.")
        return 0

    destination_client = UserMigrationClient(resolve_migration_connection(destination_profile))
    tasks, warnings = _plan_user_migrations(
        selected,
        emails,
        destination_client.query_users(include_inactive=True),
        destination_client.query_auth_mappings(),
    )
    for warning in warnings:
        click.echo(f"Warning: {warning}", err=True)

    needs_mappings = any(task.workspaces for task in tasks)
    if not tasks:
        click.echo("Successfully migrated 0 users.")
        return 0
    if destination_client.readonly and any(
        task.destination_user_id is None or task.workspaces for task in tasks
    ):
        destination_client._ensure_writable("migrate users")

    template_id: Optional[str] = None
    if needs_mappings:
        template_id = destination_client.collaborator_template_id()
        if template_id is None:
            click.echo(
                "Warning: the built-in Collaborator template was not found; workspace "
                "permissions cannot be migrated.",
                err=True,
            )
            if not questionary.confirm(
                "Continue creating users without workspace permissions?", default=False
            ).ask():
                raise click.Abort()
        else:
            click.echo(
                "Warning: migrated users receive the Collaborator role for the listed "
                "workspaces. This may grant broader access than they had on the source; "
                "review roles in the Security app after migration."
            )

    created_users = 0
    created_mappings = 0
    for task in tasks:
        user_id = task.destination_user_id
        if user_id is None:
            user_id = destination_client.create_user(task.source_user, task.email)
            created_users += 1
        if template_id:
            for workspace in task.workspaces:
                destination_client.create_auth_mapping(
                    user_id, workspace.destination_id, template_id
                )
                created_mappings += 1

    _logger.info(
        "Users migrated: users=%d created=%d auth_mappings=%d",
        len(tasks),
        created_users,
        created_mappings,
    )
    click.echo(f"Successfully migrated {len(tasks)} users.")
    return len(tasks)
