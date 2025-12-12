from typing import Any

from click.testing import CliRunner

from slcli import dff_click
from .test_utils import patch_keyring


def test_list_fields_filters_by_name(monkeypatch: Any) -> None:
    patch_keyring(monkeypatch)

    # Prepare fake fields
    fake_fields = [
        {
            "id": "1",
            "name": "PAtools-Widget",
            "displayText": "PAtools-Widget",
            "workspace": "Default",
            "type": "Text",
        },
        {
            "id": "2",
            "name": "OtherField",
            "displayText": "OtherField",
            "workspace": "Default",
            "type": "Text",
        },
        {
            "id": "3",
            "name": "patools-helper",
            "displayText": "patools-helper",
            "workspace": "Default",
            "type": "Text",
        },
    ]

    # Patch _query_all_fields to return our fake fields and get_workspace_map to a simple map
    monkeypatch.setattr(dff_click, "_query_all_fields", lambda workspace, wm: fake_fields)
    monkeypatch.setattr(dff_click, "get_workspace_map", lambda: {"Default": "Default"})

    # Build a minimal CLI and register dff commands
    from click import Group

    cli = Group()
    dff_click.register_dff_commands(cli)

    runner = CliRunner()
    result = runner.invoke(cli, ["dff", "fields", "list", "--name", "PAtools"])

    assert result.exit_code == 0
    out = result.output

    # Expect to see the two matching items in output
    assert "PAtools-Widget" in out
    assert "patools-helper" in out
    assert "OtherField" not in out
