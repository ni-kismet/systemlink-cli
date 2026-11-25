"""Prefect task for applying the reviewed user migration."""

from prefect import task
from prefect.cache_policies import NO_CACHE

from slcli.migration.users.migration import apply_user_migrations
from slcli.migration.users.models import UserMigrationSelections


@task(name="migrate-users", cache_policy=NO_CACHE)
def migrate_users_task(destination_profile: str, selections: UserMigrationSelections) -> int:
    """Apply the user migration, reconciling destination users on every run."""
    return apply_user_migrations(destination_profile, selections)
