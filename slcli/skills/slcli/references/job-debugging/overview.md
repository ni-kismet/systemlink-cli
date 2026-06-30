# SystemLink Job Debugging

Load this overview when the task is about a Systems Management Salt job that is
stuck, timing out, failing, or returning incomplete data through the Jobs API.
Use it to isolate hung `state.apply` and `cmd.run` executions before pulling in
other deployment or packaging guidance.

## When to Use

- A `state.apply` or `cmd.run` job is stuck in `INPROGRESS`
- A job fails with an unexpected retcode or empty return
- On-connect refresh jobs fail repeatedly
- `nipkg` commands fail silently because an MSI lock is held
- A Python or MSI silent installer hangs when launched through Salt
- You need to isolate which step in a multi-section SLS is hanging

## Jobs API reference

### Base URL pattern

```text
{SERVER}/nisysmgmt/v1/jobs
```

### Required headers

```text
x-ni-api-key: {API_KEY}
Content-Type: application/json
User-Agent: SystemLink-CLI/1.0
```

### Create a job

```python
job_body = {
    "tgt": [SYSTEM_ID],
    "fun": ["cmd.run"],
    "arg": [[cmd_string, {"__kwarg__": True, "shell": "cmd"}]],
    "metadata": {
        "queued": True,
        "timeout": 300,
    },
}
result = api("POST", "/nisysmgmt/v1/jobs", job_body)
jid = result["jid"]
```

### Poll a job

```python
jobs = api("GET", f"/nisysmgmt/v1/jobs?jid={jid}")
job = jobs[0] if isinstance(jobs, list) else jobs
state = job["state"]
```

### Cancel a stuck job

The cancel endpoint may return an empty body. Handle that case explicitly instead of assuming JSON.

## Debugging techniques

### 1. Detect a hung job

A job is likely hung when:

- `state` stays `INPROGRESS` and `lastUpdatedTimestamp` stops advancing
- the job has exceeded the expected operation duration
- the configured timeout has passed without a final state transition

### 2. Isolate the hanging step

If a multi-section `state.apply` hangs, break it into individual `cmd.run` jobs and poll each one separately. That is usually the fastest way to identify the failing section.

### 3. Check for lingering processes

When a job times out, child processes may still be running on the target system.
Look for installers such as `msiexec`, Python installers, or setup executables.

Critical rule:

- a running `msiexec` process holds a system-wide MSI mutex
- while that mutex is held, all `nipkg` operations may fail or hang

### 4. Restart the Salt minion after cleanup

After killing stuck installer processes, restart `nisaltminion` so the managed system returns to a clean state.

## Common pitfalls

### Pitfall 1: Path splitting in installer arguments

If `TargetDir=C:\Program Files\Python312` is passed incorrectly through Salt, the installer may receive only `C:\Program`.

Safer patterns:

- use `C:\PROGRA~1\Python312` to avoid spaces entirely
- or quote only the value portion: `TargetDir="C:\Program Files\Python312"`

Do not quote the whole `key=value` argument as a single shell token when the installer parses on `=`.

### Pitfall 2: `nipkg.py` feed name quoting

The Salt `nipkg.py` module can mishandle feed names with spaces. Patch the feed-name argument so it is quoted correctly if the environment still uses the broken implementation.

### Pitfall 3: `WixBundleInstalled = 1` blocks reinstall

If a Python installer ran once with the wrong target directory, the WiX bundle registry may treat it as already installed. Uninstall first, then rerun the installer with the corrected path.

## Escalation path

- If the failure is in package layout or `nipkg pack`, load [../nipkg/overview.md](../nipkg/overview.md).
- If the failure is in a Systems State deployment SLS that provisions a Python test app, load [../python-test/overview.md](../python-test/overview.md) after isolating the Salt failure.
