from slcli.universal_handlers import UniversalResponseHandler, FilteredResponse


def test_handle_list_response_shows_total_count(capsys):
    # Prepare a mock response with one page of 25 items and a totalCount of 556
    items = [
        {"id": str(i), "name": f"app-{i}", "workspace": "Default", "type": "WebVI"}
        for i in range(25)
    ]
    resp = FilteredResponse({"webapps": items, "totalCount": 556})

    # Call the handler with enable_pagination=False to exercise the per-page code path
    UniversalResponseHandler.handle_list_response(
        resp=resp,
        data_key="webapps",
        item_name="webapp",
        format_output="table",
        formatter_func=
        lambda it: [
            it.get("name", ""),
            it.get("workspace", ""),
            it.get("id", ""),
            it.get("type", ""),
        ],
        headers=["Name", "Workspace", "ID", "Type"],
        column_widths=[40, 30, 36, 16],
        empty_message="No webapps found.",
        enable_pagination=False,
        page_size=25,
        total_count=556,
        shown_count=25,
    )

    captured = capsys.readouterr()
    assert "Showing 25 of 556 webapp(s). 531 more available." in captured.out
