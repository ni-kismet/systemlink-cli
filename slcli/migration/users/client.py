"""Profile-bound User Service and authorization API operations."""

from typing import Dict, List, Optional, Union

import click
import requests
from pydantic import Field, field_validator

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

PAGE_SIZE = 100


class User(ApiModel):
    """A user record returned by User Service."""

    id: str
    type: str = "user"
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
    users: List[User]
    continuation_token: Optional[str] = None


class Policy(ApiModel):
    """A user authorization policy."""

    id: str
    name: str
    built_in: bool = False
    template_id: Optional[str] = None
    workspace: Optional[str] = None


class _PolicyPage(ApiModel):
    policies: List[Policy]


class AuthMappingSelector(ApiModel):
    """A selector identifying the subject of an authorization mapping."""

    key: str
    value: str


class AuthMapping(ApiModel):
    """An authorization mapping to a workspace."""

    type: str
    selector: AuthMappingSelector
    workspace: Optional[str] = None


class _AuthMappingPage(ApiModel):
    auth_mappings: List[AuthMapping]


class _PolicyTemplate(ApiModel):
    id: str


class _PolicyTemplatePage(ApiModel):
    policy_templates: List[_PolicyTemplate]


class _CreatedUser(ApiModel):
    id: str


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

    def query_users(self, include_inactive: bool = False) -> List[User]:
        """Return users across all pages, optionally including non-active accounts."""
        url = f"{self._base_url}/niuser/v1/users/query"
        payload: Dict[str, object] = {"take": PAGE_SIZE}
        if not include_inactive:
            payload["filter"] = 'status = "active"'
        users: List[User] = []
        while True:
            response = self._session.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            page = _UserPage.model_validate(response.json())
            users.extend(page.users)
            if not page.continuation_token:
                return users
            payload = {**payload, "continuationToken": page.continuation_token}

    def query_policies(self) -> List[Policy]:
        """Return every policy, following the authorization service's offset pages."""
        url = f"{self._base_url}/niauth/v1/policies"
        policies: List[Policy] = []
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

    def query_auth_mappings(self) -> List[AuthMapping]:
        """Return all user-ID auth-mappings, following offset pages."""
        url = f"{self._base_url}/niuser/v1/auth-mappings"
        mappings: List[AuthMapping] = []
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

    def create_user(self, source_user: User) -> str:
        """Create a user using the email as the default identity-provider ID."""
        self._ensure_writable("create users")
        response = self._write_session.post(
            f"{self._base_url}/niuser/v1/users",
            json={
                "type": "user",
                "firstName": source_user.first_name or "",
                "lastName": source_user.last_name or "",
                "email": source_user.email,
                "phone": "",
                "niuaId": source_user.email,
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
