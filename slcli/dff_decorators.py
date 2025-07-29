"""Reusable Click decorators for CLI commands."""

import click


def workspace_option(help_text: str = "Filter by workspace name or ID"):
    """Standard workspace filtering option decorator."""
    return click.option("--workspace", "-w", help=help_text)


def format_option(default: str = "table", help_text: str = "Output format: table or json"):
    """Standard format option decorator."""
    return click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default=default,
        show_default=True,
        help=help_text,
    )


def take_option(default: int = 1000, help_text: str = "Maximum number of items to return"):
    """Standard take option decorator for pagination."""
    return click.option(
        "--take",
        default=default,
        show_default=True,
        help=help_text,
    )


def output_option(help_text: str = "Output file path"):
    """Standard output file option decorator."""
    return click.option("--output", "-o", help=help_text)


def id_option(required: bool = True, help_text: str = "ID of the item"):
    """Standard ID option decorator."""
    return click.option(
        "--id",
        "-i",
        required=required,
        help=help_text,
    )


def file_option(required: bool = True, help_text: str = "Input file path"):
    """Standard file input option decorator."""
    return click.option(
        "--file",
        "-f",
        required=required,
        help=help_text,
    )


def confirmation_option(prompt_text: str = "Are you sure?"):
    """Standard confirmation option decorator."""
    return click.confirmation_option(prompt=prompt_text)


def list_command_options(
    workspace_help: str = "Filter by workspace name or ID",
    take_default: int = 1000,
    take_help: str = "Maximum number of items to return",
    format_help: str = "Output format: table or json",
):
    """Combined decorator for standard list command options."""

    def decorator(func):
        func = workspace_option(workspace_help)(func)
        func = take_option(take_default, take_help)(func)
        func = format_option("table", format_help)(func)
        return func

    return decorator


def export_command_options(
    id_help: str = "ID of the item to export",
    output_help: str = "Output JSON file (default: auto-generated)",
):
    """Combined decorator for standard export command options."""

    def decorator(func):
        func = id_option(True, id_help)(func)
        func = output_option(output_help)(func)
        return func

    return decorator


def import_command_options(file_help: str = "Input JSON file"):
    """Combined decorator for standard import command options."""

    def decorator(func):
        func = file_option(True, file_help)(func)
        return func

    return decorator


def delete_command_options(
    id_help: str = "ID(s) of the item(s) to delete",
    file_help: str = "JSON file containing IDs to delete",
    confirmation_prompt: str = "Are you sure you want to delete these items?",
):
    """Combined decorator for standard delete command options."""

    def decorator(func):
        func = click.option(
            "--id",
            "-i",
            "item_ids",
            multiple=True,
            help=id_help,
        )(func)
        func = click.option(
            "--file",
            "-f",
            "input_file",
            help=file_help,
        )(func)
        func = confirmation_option(confirmation_prompt)(func)
        return func

    return decorator


def get_command_options(
    id_help: str = "ID of the item to retrieve", format_help: str = "Output format: table or json"
):
    """Combined decorator for standard get command options."""

    def decorator(func):
        func = id_option(True, id_help)(func)
        func = format_option("json", format_help)(func)
        return func

    return decorator


def init_command_options(
    name_help: str = "Name of the item (will prompt if not provided)",
    workspace_help: str = "Workspace name or ID (will prompt if not provided)",
    output_help: str = "Output file path (default: auto-generated)",
):
    """Combined decorator for standard init command options."""

    def decorator(func):
        func = click.option(
            "--name",
            "-n",
            help=name_help,
        )(func)
        func = workspace_option(workspace_help)(func)
        func = output_option(output_help)(func)
        return func

    return decorator


class DFFDecorators:
    """Specific decorators for DFF commands."""

    @staticmethod
    def config_list_options():
        """Decorator for DFF configuration list command options."""
        return list_command_options(
            workspace_help="Filter by workspace name or ID",
            take_help="Maximum number of configurations to return",
        )

    @staticmethod
    def groups_list_options():
        """Decorator for DFF groups list command options."""
        return list_command_options(
            workspace_help="Filter by workspace name or ID",
            take_help="Maximum number of groups to return",
        )

    @staticmethod
    def fields_list_options():
        """Decorator for DFF fields list command options."""
        return list_command_options(
            workspace_help="Filter by workspace name or ID",
            take_help="Maximum number of fields to return",
        )

    @staticmethod
    def table_query_options():
        """Specific options for table query command."""

        def decorator(func):
            func = click.option(
                "--workspace",
                "-w",
                required=True,
                help="Workspace name or ID to query tables for",
            )(func)
            func = click.option(
                "--resource-id",
                "-i",
                required=True,
                help="Resource ID to filter by",
            )(func)
            func = click.option(
                "--resource-type",
                "-r",
                required=True,
                help="Resource type to filter by",
            )(func)
            func = click.option(
                "--keys",
                "-k",
                multiple=True,
                help="Table keys to filter by (can be specified multiple times)",
            )(func)
            func = take_option(1000, "Maximum number of table properties to return")(func)
            func = click.option(
                "--continuation-token",
                "-c",
                help="Continuation token for pagination",
            )(func)
            func = click.option(
                "--return-count",
                is_flag=True,
                help="Return the total count of accessible table properties",
            )(func)
            func = format_option()(func)
            return func

        return decorator

    @staticmethod
    def config_init_options():
        """Decorator for DFF configuration init command options."""
        return init_command_options(
            name_help="Configuration name (will prompt if not provided)",
            workspace_help="Workspace name or ID (will prompt if not provided)",
        )
