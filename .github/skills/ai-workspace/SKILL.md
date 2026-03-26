---
name: ai-workspace
description: Convention for storing AI-generated intermediate files (scripts, logs, context, temp data) under build/ai/ in the current git repository. Use this skill whenever generating, writing, or referencing scratch files, intermediate artifacts, logs, captured context, or temporary scripts during any AI-assisted workflow. All other skills that produce intermediate or temporary files should follow this convention.
---

# AI Workspace Directory

All AI-generated intermediate and temporary files go under **`build/ai/`**
relative to the git repository root.

## Rules

1. **Single output root** — always use `build/ai/` (never `/tmp`, `$TEMP`,
   the user's home directory, or other ad-hoc locations).
2. **Create on demand** — ensure the directory exists before writing files.
3. **Do not delete** — leave generated files in place after use. They serve as
   an audit trail and aid debugging. Do not add cleanup steps that remove them.
   Users may periodically clean `build/ai/` manually.
4. **Git-ignored** — `build/` is already in `.gitignore`, so these files will
   never be committed accidentally.
5. **Organize with subdirectories** when a task produces many files:
   ```
   build/ai/<skill-name>/
   ├── scripts/       # generated scripts
   ├── logs/          # command output, API responses
   ├── context/       # captured context, summaries
   └── <task-name>/   # task-specific scratch area
   ```
6. **Unique names** — when collisions are possible, include a timestamp or
   short identifier in the filename (e.g. `query-2026-03-06T14-30.json`).
7. **UTF-8 encoding** — write all generated text files as UTF-8.

## What belongs here

- Generated shell / Python / PowerShell scripts
- Command output and log captures
- API responses saved for later reference
- Context snapshots, summaries, or extracted data
- Any other scratch or intermediate file an AI workflow produces

## What does NOT belong here

- Final deliverables the user asked for (place where the user expects them)
- Source code changes (edit files in-place in the repo)
- Permanent configuration (use the repo's normal config locations)
