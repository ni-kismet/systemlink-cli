---
name: eval-skill-gating
description: Run the full slcli gating eval workflow end to end: prepare an iteration, generate prompts, execute with_skill and without_skill runs via isolated subagents, grade, benchmark, and regenerate the static review page.
argument-hint: Optional key=value args such as iteration_dir="..." max_parallel=3 max_tool_calls=8 max_minutes=3 force=true
agent: agent
---

## Summary

Run the `slcli` gating eval workflow from one parent Copilot chat.

This prompt should:

1. prepare or reuse a gating iteration workspace
2. generate executor prompts
3. execute all `with_skill` and `without_skill` runs with isolated subagents
4. grade and aggregate the iteration
5. regenerate the static review page
6. report the populated run directories, benchmark result, and `review.html` path

## Arguments

Use `key=value` arguments. Quote values that contain spaces.

- `iteration_dir` (optional): Existing prepared iteration directory to use instead of creating a new one
- `max_parallel` (optional): Maximum parallel subagents. Default: `3`
- `max_tool_calls` (optional): Per-run fail-fast tool-call budget. Default: `8`
- `max_minutes` (optional): Per-run fail-fast active-work budget. Default: `3`
- `force` (optional): Regenerate prompts and grading artifacts when needed. Default: `true`

## Slash Commands

```bash
/eval-skill-gating
/eval-skill-gating iteration_dir="slcli/skills/slcli-workspace/iteration-4"
/eval-skill-gating max_parallel=2 max_tool_calls=6 max_minutes=2.5
```

## Procedure

You are running the `slcli` gating eval workflow. Execute this sequence autonomously.

### 1. Resolve the iteration workspace

- If `iteration_dir` was provided, use it.
- Otherwise run:

```bash
python slcli/skills/slcli/scripts/prepare_eval_workspace.py --suite gating --isolate-baseline
```

- Capture the printed iteration directory and use it for all later steps.

### 2. Generate executor prompts

Run:

```bash
python slcli/skills/slcli/scripts/prepare_eval_prompts.py <ITERATION_DIR> \
  --force \
  --max-tool-calls <MAX_TOOL_CALLS> \
  --max-minutes <MAX_MINUTES>
```

### 3. Read the run inputs

- Read `<ITERATION_DIR>/iteration_manifest.json`.
- Discover every `executor_prompt.txt` under `<ITERATION_DIR>`.

### 4. Execute the eval runs

- Use one parent conversation only as the orchestrator.
- Do not answer run prompts directly in the parent chat context.
- Execute each prepared run in a fresh stateless subagent.
- Never reuse a subagent across runs.
- Parallelize independent runs modestly, up to `max_parallel`.

For each run:

- Read that run's `executor_prompt.txt`.
- For `with_skill`, allow the subagent to read and use the `slcli` skill.
- For `without_skill`, do not load the skill and use the isolated baseline repo path named in the prompt when present.
- Respect the fail-fast budget written into the executor prompt.
- If the run converges, save the final answer to `outputs/response.txt`.
- If the run does not converge inside budget, save the best grounded partial answer to `outputs/response.txt` and add `outputs/notes.txt` with a brief failure reason.
- Never write outside the run's `outputs/` directory.
- Do not overwrite an already populated response unless it is obviously a placeholder.

### 5. Grade and aggregate

After all runs are attempted, run:

```bash
python slcli/skills/slcli/scripts/benchmark_iteration.py --force <ITERATION_DIR>
```

### 6. Regenerate the static review page

Run:

```bash
python slcli/skills/slcli/scripts/render_eval_review.py <ITERATION_DIR>
```

### 7. Final report

Report:

- the iteration directory used
- which run directories were populated
- any runs that failed to converge inside budget
- whether benchmark generation succeeded
- the `benchmark.json`, `benchmark.md`, and `review.html` paths
- the overall with-skill versus baseline pass-rate summary when available

## Constraints

- Treat the parent chat as contaminated shared context; only subagents should execute eval prompts.
- Keep concurrency modest even if more parallelism is available.
- Continue the batch if a single run fails.
- Keep all saved responses grounded in supported `slcli` commands and workflows.
