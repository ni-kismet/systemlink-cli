"""Models for users selected to be migrated."""

from dataclasses import dataclass
from typing import List, Tuple

from pydantic import model_validator

from slcli.migration.schema import VersionedModel
from slcli.migration.users.client import User
from slcli.migration.workspaces import MappedWorkspace


@dataclass(frozen=True)
class UserToMigrate:
    """A source user and migrated workspaces they will be authorized for."""

    user: User
    workspaces: Tuple[MappedWorkspace, ...]


class UserMigrationSelections(VersionedModel):
    """Source users selected for migration, persisted as the Prefect result of the review task."""

    users: List[UserToMigrate]

    @model_validator(mode="after")
    def _validate_review(self) -> "UserMigrationSelections":
        ids = [user.user.id for user in self.users]
        if len(set(ids)) != len(ids):
            raise ValueError("User review contains duplicate source IDs")
        for user in self.users:
            if not user.user.email:
                raise ValueError("User is missing email")
        return self
