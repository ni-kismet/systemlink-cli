"""Interactive selection of users and their destination emails."""

from dataclasses import replace
from typing import List

import click
import questionary
from prompt_toolkit.utils import get_cwidth

from slcli.migration.users.models import UserToMigrate


def select_users(candidates: List[UserToMigrate]) -> List[UserToMigrate]:
    """Ask which candidates should be migrated."""
    column_gap = 3
    name_column_width = column_gap + max(
        (get_cwidth(_formatted_name(candidate)) for candidate in candidates), default=column_gap + 1
    )
    email_column_width = column_gap + max(
        (get_cwidth(candidate.user.email or "") for candidate in candidates), default=column_gap + 1
    )
    choices = [
        questionary.Choice(
            _format_row(candidate, name_column_width, email_column_width),
            value=candidate,
            checked=True,
        )
        for candidate in candidates
    ]
    selected = questionary.checkbox(
        "Select users to migrate. Migrated users are granted the 'Collaborator' role in the indicated workspaces. "
        "Note that this potentially grants permissions beyond what the user had in the original workspaces. "
        "After migration, use SystemLink's Access Control hub to change assigned roles as needed.",
        choices=choices,
    ).ask()
    if selected is None:
        raise click.Abort()
    return [candidate for candidate in candidates if candidate in selected]


def resolve_emails(candidates: List[UserToMigrate]) -> List[UserToMigrate]:
    """Resolve destination emails, prompting for missing ones."""
    have_emails = []
    for candidate in candidates:
        email = (candidate.user.email or "").strip()
        if not email:
            entered = click.prompt(
                f"An email is required for authentication but was missing for user "
                f"'{_formatted_name(candidate)}'. Enter it now, or leave blank to skip "
                "migrating this user",
                default="",
                show_default=False,
            )
            email = entered.strip()
            if not email:
                click.echo(f"Skipping user '{_formatted_name(candidate)}'.")
                continue
        have_emails.append(
            replace(candidate, user=candidate.user.model_copy(update={"email": email}))
        )
    return have_emails


def _format_row(candidate: UserToMigrate, name_column_width: int, email_column_width: int) -> str:
    name = _formatted_name(candidate)
    workspaces = ", ".join(workspace.destination_name for workspace in candidate.workspaces)
    name_column_padding = f"{' ' * (name_column_width - get_cwidth(name))}"
    email_column_padding = f"{' ' * (email_column_width - get_cwidth(candidate.user.email or ''))}"
    return (
        f"{name}{name_column_padding}{candidate.user.email or ''}{email_column_padding}{workspaces}"
    )


def _formatted_name(candidate: UserToMigrate) -> str:
    return " ".join(part for part in (candidate.user.first_name, candidate.user.last_name) if part)
