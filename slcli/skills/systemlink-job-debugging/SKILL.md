---
name: systemlink-job-debugging
description: >-
  Debug NI SystemLink Salt jobs dispatched through the Systems Management Jobs
  API. Use when jobs are stuck, time out, return empty data, or fail with
  unexpected retcodes.
argument-hint: >-
  Describe the job symptom, the Salt function or state being run, and any known
  timeout or return data.
---

# SystemLink Job Debugging

Use this skill when the main problem is isolating or recovering a Salt job that
was launched through the Jobs API.

## Reference docs

| Need | Read |
| --- | --- |
| Jobs API polling, hang isolation, and Windows Salt pitfalls | [overview.md](../slcli/references/job-debugging/overview.md) |
| Related CLI command syntax | [commands.md](../slcli/references/commands.md#system--system-fleet-management) |

## Default approach

1. Confirm whether the job is actually stuck or just slow.
2. Break multi-step states into isolated `cmd.run` slices when the hanging step is unknown.
3. Check for lingering installer processes and MSI locks on the target system.
4. Restart the Salt minion only after identifying or killing the blocking child process.