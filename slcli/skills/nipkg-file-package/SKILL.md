---
name: nipkg-file-package
description: >-
  Build NI Package Manager file packages (`.nipkg`) for Windows and SystemLink
  deployment. Use when the task is about package layout, target roots, control
  metadata, or troubleshooting `nipkg pack` failures.
argument-hint: >-
  Describe the payload you need to package, the intended install target, and the
  current `nipkg` error or packaging question.
---

# NI File Packages

Use this skill when the task is specifically about assembling or fixing an
NI Package Manager file package.

## Reference docs

| Need | Read |
| --- | --- |
| Package structure, control metadata, and target roots | [overview.md](../slcli/references/nipkg/overview.md) |
| Related CLI and workflow guidance | [commands.md](../slcli/references/commands.md) |

## Default approach

1. Start from the required top-level package structure.
2. Validate the target root names before debugging deeper.
3. Keep `Depends` minimal and only for packages guaranteed to exist on the target systems.
4. Unpack the built `.nipkg` to verify the output before publishing it.