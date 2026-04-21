# Troubleshooting & Tips

Common issues and workarounds when using `slcli` or scripting against SystemLink APIs.

## Workspace IDs vs names

Some API endpoints (notably **file upload**) require the workspace **UUID**, not
the human-readable name. When a command fails with a 400 error and you passed a
workspace name, retry with the workspace ID:

```bash
# Resolve workspace name → ID
slcli workspace list -f json | jq '.[] | select(.name=="MyWorkspace") | .id'

# Then use the ID
slcli file upload "file.pdf" -w "d503640b-db60-41c7-9b97-4ce2e53851f3"
```

As a general rule, **prefer workspace IDs over names** in scripted or automated
workflows to avoid ambiguity.

## Python scripting with slcli internals

When writing helper scripts that call SystemLink APIs, always use
`make_api_request` from `slcli.utils` instead of raw `requests.post/get`.
`make_api_request` handles authentication, SSL trust, and error formatting:

```python
from slcli.utils import make_api_request, get_base_url

resp = make_api_request(
    "POST",
    f"{get_base_url()}/nitestmonitor/v2/update-products",
    payload={...},
)
data = resp.json()
```

Do **not** use `requests` directly — it will fail with `ConnectionResetError`
on servers that use self-signed or enterprise SSL certificates.

## Windows terminal encoding

On Windows, set `PYTHONUTF8=1` before running slcli to avoid `charmap` codec
errors when the output contains Unicode characters (✓, ✗, box-drawing):

```powershell
$env:PYTHONUTF8 = "1"
slcli spec list --product "My Product" --take 25
```

## PowerShell quoting

PowerShell mangles inline Python f-strings that contain dictionary key access
(e.g. `p["name"]`). When running Python one-liners from PowerShell:

- Write the script to a `.py` file and execute it, or
- Use `python -m <module>` to run a module, or
- Avoid f-strings with bracket notation in `-c` arguments.

## Large file uploads

File uploads to SystemLink can take 30+ seconds for multi-MB PDFs. If the
command appears to hang, give it time — the upload is still in progress.
Set a generous timeout (60–120 s) when automating uploads.
