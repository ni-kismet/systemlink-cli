---
name: systemlink-job-debugging
description: >-
  Debug NI SystemLink Salt jobs dispatched via the Systems Management Jobs API.
  Use when a state.apply or cmd.run job is stuck INPROGRESS, times out, fails
  with an unexpected retcode, or produces no return data. Covers the Jobs API
  polling pattern, common Salt/cmd.run pitfalls on Windows (MSI locks, quoting,
  path splitting), techniques for isolating which step in a multi-step SLS hangs,
  and how to cancel or recover from stuck jobs. Also covers the on-connect
  refresh job pattern and nipkg.py module issues.
compatibility: >-
  Requires network access to a SystemLink Enterprise server with the Systems
  Management (nisysmgmt) API. Python 3.10+ with urllib or requests.
metadata:
  author: ni-kismet
  version: "1.0"
---

# SystemLink Job Debugging

Debug Salt jobs dispatched to managed systems via the SystemLink Jobs API.

## When to Use

- A `state.apply` or `cmd.run` job is stuck in INPROGRESS for minutes/hours
- A job fails with an unexpected retcode or empty return
- On-connect refresh jobs consistently fail with retcode `-2147220448`
- nipkg commands fail silently due to MSI mutex locks
- A Python/MSI silent installer hangs when run through Salt
- You need to isolate which step in a multi-section SLS is causing a hang

## Jobs API Reference

### Base URL pattern
```
{SERVER}/nisysmgmt/v1/jobs
```

### Required headers
```
x-ni-api-key: {API_KEY}
Content-Type: application/json
User-Agent: SystemLink-CLI/1.0
```

### Create a job

```python
job_body = {
    "tgt": [SYSTEM_ID],           # list of system IDs
    "fun": ["cmd.run"],           # Salt function(s)
    "arg": [[cmd_string, {"__kwarg__": True, "shell": "cmd"}]],
    "metadata": {
        "queued": True,
        "timeout": 300            # seconds before server times out the job
    }
}
result = api("POST", "/nisysmgmt/v1/jobs", job_body)
jid = result["jid"]
```

### Poll a job

```python
jobs = api("GET", f"/nisysmgmt/v1/jobs?jid={jid}")
# IMPORTANT: Response is a LIST, not a dict
job = jobs[0] if isinstance(jobs, list) else jobs
state = job["state"]  # INQUEUE, INPROGRESS, SUCCEEDED, FAILED, CANCELED, TIMED_OUT
```

### Cancel a stuck job

```python
body = [{"jid": jid, "systemId": SYSTEM_ID}]
# IMPORTANT: cancel-jobs returns EMPTY body (not JSON)
resp = urllib.request.urlopen(req, context=ctx)
raw = resp.read().decode()
if not raw.strip():
    return {}  # handle empty response
```

### Key fields on a job object

| Field | Notes |
|-------|-------|
| `state` | INQUEUE → INPROGRESS → SUCCEEDED/FAILED/CANCELED/TIMED_OUT |
| `retcode` | `None` while running; `0` on success |
| `return` | Salt function return value (may be empty on failure) |
| `createdTimestamp` | ISO-8601 creation time |
| `lastUpdatedTimestamp` | Stops updating if Salt process hangs |
| `fun` | The Salt function(s) that were called |

## Debugging Techniques

### 1. Detect a hung job

A job is likely hung when:
- `state` is `INPROGRESS` but `lastUpdatedTimestamp` stopped advancing
  (more than 2 minutes between updates)
- The job has been INPROGRESS longer than the expected operation duration
- The `metadata.timeout` has been reached but the job hasn't transitioned

### 2. Isolate the hanging step in a multi-section SLS

When a `state.apply` with multiple sections hangs, you cannot tell from the
Jobs API which section is stuck. **Run each section as an individual `cmd.run`
job** to isolate the problem:

```python
def run_cmd(description, cmd, timeout=120):
    """Submit a single cmd.run job and poll for completion."""
    job_body = {
        "tgt": [SYSTEM_ID],
        "fun": ["cmd.run"],
        "arg": [[cmd, {"__kwarg__": True, "shell": "cmd"}]],
        "metadata": {"queued": True, "timeout": timeout},
    }
    result = api("POST", "/nisysmgmt/v1/jobs", job_body)
    jid = result["jid"]

    for i in range(timeout // 5 + 12):
        time.sleep(5)
        job = api("GET", f"/nisysmgmt/v1/jobs?jid={jid}")
        if isinstance(job, list):
            job = job[0]
        state = job.get("state", "UNKNOWN")
        print(f"  [{(i+1)*5:3d}s] {state}")
        if state in ("SUCCEEDED", "FAILED", "CANCELED", "TIMED_OUT"):
            return state == "SUCCEEDED"
    return False

# Run each SLS step individually
results = []
results.append(("Step 1", run_cmd("Description", "command here", timeout=60)))
results.append(("Step 2", run_cmd("Description", "command here", timeout=300)))
# ... etc

# Print summary
for name, ok in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
```

### 3. Check for lingering processes on the target system

When a job times out, the Salt-spawned child process may keep running:

```powershell
# Check for installer processes holding MSI locks
Get-Process | Where-Object { $_.Name -match 'msiexec|python-3|setup' } | Select-Object Name, Id, StartTime

# Kill stuck processes (requires elevation)
Start-Process powershell -Verb RunAs -ArgumentList '-Command', 'Stop-Process -Id <PID> -Force'
```

**Critical**: A running `msiexec` process holds a system-wide MSI mutex lock.
While this lock is held, ALL nipkg commands will fail or hang, including
`feed-add`, `feed-list`, `install`, and `info`. Always kill lingering MSI
processes before retrying nipkg operations.

### 4. Restart the Salt minion after killing stuck processes

```powershell
Start-Process powershell -Verb RunAs -ArgumentList '-Command', `
    'Stop-Process -Id <STUCK_PID> -Force; Start-Sleep 2; Restart-Service nisaltminion -Force'
```

The Salt minion PID can be found at:
```powershell
Get-Process | Where-Object { $_.Name -eq 'python' } | Where-Object { $_.Path -match 'salt' }
# Or check the service:
Get-WmiObject Win32_Service -Filter "Name='nisaltminion'" | Select-Object ProcessId
```

## Common Pitfalls

### Pitfall 1: Path splitting in installer arguments

**Problem**: When passing `TargetDir=C:\Program Files\Python312` through Salt's
`cmd.run`, the space in `Program Files` causes the argument to split. The
installer receives `TargetDir=C:\Program` and installs to the wrong location.

**Symptom**: Python installs to `C:\Program\` instead of `C:\Program Files\Python312\`.
The installer log shows `TargetDir = C:\Program` and `WixBundleInstalled = 1`.
The installer exits code 0 on subsequent runs (thinks it's already installed).

**Root cause**: Quoting `"TargetDir=C:\Program Files\Python312"` wraps the
whole key=value pair, but WiX Burn parses the `=` first. The value after `=`
is `C:\Program` (up to the space), and `Files\Python312"` becomes a separate arg.

**Fix for SLS / cmd.run**: Use the short path `PROGRA~1` to avoid spaces entirely:

```yaml
install-python:
  cmd.run:
    - name: >-
        "C:\Windows\Temp\python-3.12.9-amd64.exe"
        /quiet InstallAllUsers=1 PrependPath=1
        TargetDir=C:\PROGRA~1\Python312
        Include_launcher=1
    - shell: cmd
```

Or escape the quotes so they survive Salt → cmd.exe → installer:

```yaml
    - name: >-
        C:\Windows\Temp\python-3.12.9-amd64.exe
        /quiet InstallAllUsers=1 PrependPath=1
        TargetDir="C:\Program Files\Python312"
        Include_launcher=1
```

Note: When TargetDir is unquoted and uses `key=value` syntax (no quotes around
the whole expression), the installer receives the value correctly.

**Fix for Python cmd string in Jobs API**:

```python
# WRONG - quotes around the whole key=value
cmd = '"C:\\Windows\\Temp\\python-3.12.9-amd64.exe" /quiet "TargetDir=C:\\Program Files\\Python312"'

# RIGHT - use short path to avoid spaces
cmd = '"C:\\Windows\\Temp\\python-3.12.9-amd64.exe" /quiet TargetDir=C:\\PROGRA~1\\Python312'

# RIGHT - quotes only around the value portion
cmd = 'C:\\Windows\\Temp\\python-3.12.9-amd64.exe /quiet TargetDir="C:\\Program Files\\Python312"'
```

### Pitfall 2: nipkg.py feed name quoting

**Problem**: The Salt `nipkg.py` module's `_add_new_repo` function builds a
command with `--name={0}` but feed names may contain spaces.

**Fix**: Patch `_add_new_repo` in
`C:\ProgramData\National Instruments\salt\var\extmods\modules\nipkg.py`
around line 1492:

```python
# Before (broken with spaces):
cmd.append('--name={0}'.format(alias))

# After (handles spaces):
cmd.append('--name="{0}"'.format(alias))
```

### Pitfall 3: WixBundleInstalled = 1 preventing reinstall

**Problem**: After a Python installer runs to the wrong directory, the
WiX bundle registry marks it as installed. Running the installer again with
the correct TargetDir does nothing (exits 0 immediately).

**Fix**: Uninstall first, then reinstall:

```powershell
# Uninstall
& "C:\Windows\Temp\python-3.12.9-amd64.exe" /uninstall /quiet

# Wait for completion, then reinstall with corrected path
& "C:\Windows\Temp\python-3.12.9-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 TargetDir=C:\PROGRA~1\Python312
```

Or use `REINSTALLMODE=amus` to force a reinstall to the correct location.

### Pitfall 4: cancel-jobs API returns empty body

**Problem**: `POST /nisysmgmt/v1/cancel-jobs` returns HTTP 200 with an empty
response body. Calling `json.loads("")` raises `JSONDecodeError`.

**Fix**: Always check for empty responses:

```python
raw = urllib.request.urlopen(req, context=ctx).read().decode()
if not raw.strip():
    return {}
return json.loads(raw)
```

### Pitfall 5: Jobs API returns a list, not a dict

**Problem**: `GET /nisysmgmt/v1/jobs?jid=X` returns a JSON **list** (array),
not a dict. Code that does `jobs["state"]` will fail.

**Fix**:

```python
jobs = api("GET", f"/nisysmgmt/v1/jobs?jid={jid}")
if isinstance(jobs, list) and jobs:
    job = jobs[0]
```

### Pitfall 6: On-connect refresh jobs fail with retcode -2147220448

**Problem**: SystemLink's automatic on-connect jobs (which call `pkg.list_repos`,
`pkg.info_installed`, etc.) consistently fail with retcode `-2147220448`.

**Context**: This is a known issue that may relate to MSI mutex contention,
feed configuration issues, or Salt module load failures. The minion usually
recovers and subsequent manual jobs succeed.

**Workaround**: Submit a manual refresh job after confirming the system is
CONNECTED:

```python
job_body = {
    "tgt": [SYSTEM_ID],
    "fun": ["pkg.list_repos", "pkg.info_installed"],
    "arg": [[], [{"__kwarg__": True, "attr": ["description", "displayname", "displayversion"]}]],
    "metadata": {"queued": True, "timeout": 300}
}
```

## Diagnostic Checklist

When a job hangs or fails:

1. **Check job state and timestamps**: Is `lastUpdatedTimestamp` still advancing?
2. **Check for lingering processes**: `Get-Process msiexec, python-3*` — MSI locks block everything
3. **Kill stuck processes**: Terminate any orphaned installer/MSI processes
4. **Check the Salt minion**: Is `nisaltminion` service running? Restart if needed
5. **Isolate the step**: Run each SLS section as individual `cmd.run` jobs
6. **Check quoting**: Paths with spaces are the #1 cause of silent failures on Windows
7. **Check installer logs**: Use `/log C:\temp\install.log` to get WiX Burn output
8. **Look for WixBundleInstalled=1**: Previous bad install may prevent correct reinstall
9. **Verify the target path**: Check registry keys and actual filesystem for where things landed
10. **Check MSI mutex**: Only one MSI operation can run system-wide at a time
