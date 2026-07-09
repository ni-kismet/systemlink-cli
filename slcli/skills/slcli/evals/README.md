# slcli Eval Workflow

This directory contains the eval corpus for the repo-local `slcli` skill.
Use the `gating` suite as the normal short feedback loop after a skill edit.

## Gating Workflow

Run the following from the repository root.

### 1. Run the single prompt

Use the repo prompt in Copilot Chat:

```text
/eval-skill-gating
```

Optional examples:

```text
/eval-skill-gating iteration_dir="slcli/skills/slcli-workspace/iteration-4"
/eval-skill-gating max_parallel=2 max_tool_calls=6 max_minutes=2.5
```

The prompt performs the full gating workflow:

- prepare or reuse a gating iteration
- generate executor prompts and orchestration metadata
- render the orchestration plan
- execute `with_skill` and `without_skill` runs via isolated subagents
- grade and aggregate the iteration
- regenerate `review.html`

### 2. What the prompt runs under the hood

If you need to run the flow manually, these are the underlying steps.

#### Prepare a fresh gating workspace

```bash
python slcli/skills/slcli/scripts/prepare_eval_workspace.py --suite gating
```

This prints a new iteration directory such as:

```text
slcli/skills/slcli-workspace/iteration-1
```

#### Generate executor prompts and the orchestration manifest

```bash
python slcli/skills/slcli/scripts/prepare_eval_prompts.py \
  slcli/skills/slcli-workspace/iteration-1 \
  --max-tool-calls 8 \
  --max-minutes 3 \
  --max-parallel 3
```

This writes:

- one `executor_prompt.txt` per prepared run
- `orchestration_manifest.json` at the iteration root

#### Render the parent-chat execution plan

```bash
python slcli/skills/slcli/scripts/render_orchestration_plan.py \
  slcli/skills/slcli-workspace/iteration-1 \
  --output slcli/skills/slcli-workspace/iteration-1/orchestration-plan.md
```

#### Execute the runs in Copilot

Use [COPILOT_BATCH_RUN_PROMPT.md](./COPILOT_BATCH_RUN_PROMPT.md) together with
the generated `orchestration_manifest.json` or `orchestration-plan.md`.

Recommended execution pattern:

1. Use one parent chat as the orchestrator.
2. Run each prepared eval in a fresh stateless subagent.
3. Let `with_skill` runs load the `slcli` skill.
4. Do not let `without_skill` runs load the skill.
5. Keep concurrency modest, usually 2 to 4 runs at a time.
6. If a run exceeds its budget, save the best grounded `response.txt`, add a short `notes.txt`, and continue.

Each run saves artifacts under its own `outputs/` directory.

#### Grade and aggregate the iteration

```bash
python slcli/skills/slcli/scripts/benchmark_iteration.py --force \
  slcli/skills/slcli-workspace/iteration-1
```

This grades populated runs and writes `benchmark.json` plus `benchmark.md`.

#### Regenerate the review page

```bash
python slcli/skills/slcli/scripts/render_eval_review.py \
  slcli/skills/slcli-workspace/iteration-1
```

This writes `review.html` in the iteration directory.

## What Good Looks Like

- `with_skill` should beat the baseline on the gating suite.
- Failures should point to missing skill behavior, not to ambiguous eval wording.
- If both configs pass easily, the eval may be too weak.
- If both configs fail, tighten the prompt or grading rules before changing the skill.

## Files in This Directory

- `evals.json`: prompts, fixtures, and grading rules
- `files/`: input fixtures for file-backed evals
- `../../../.github/prompts/eval-skill-gating.prompt.md`: one-shot gating eval prompt
- `COPILOT_BATCH_RUN_PROMPT.md`: parent-chat orchestration prompt
- `../scripts/prepare_eval_workspace.py`: scaffolds an iteration directory
- `../scripts/prepare_eval_prompts.py`: writes executor prompts and orchestration metadata
- `../scripts/render_orchestration_plan.py`: renders a batch-by-batch parent-chat plan
- `../scripts/benchmark_iteration.py`: grades and aggregates a full iteration
- `../scripts/render_eval_review.py`: writes the static review page

## Broader Coverage

Use `regression` instead of `gating` before you consider the skill stable.

## What To Commit

Commit the eval harness and definitions:

- `slcli/skills/slcli/SKILL.md`
- `slcli/skills/slcli/evals/evals.json`
- `slcli/skills/slcli/evals/files/`
- `slcli/skills/slcli/evals/README.md`
- `slcli/skills/slcli/evals/COPILOT_BATCH_RUN_PROMPT.md`
- `slcli/skills/slcli/scripts/`
- `slcli/skills/slcli/.github/prompts/` or repo-level prompt files that drive the workflow

Do not usually commit run artifacts:

- `slcli/skills/slcli-workspace/`
- per-run `outputs/response.txt`
- per-run `grading.json`
- generated `benchmark.json` and `benchmark.md`
- generated `review.html`

Treat the checked-in files as the reproducible test harness and the workspace
artifacts as local experiment output unless you intentionally want to preserve a
specific benchmark snapshot for review or release documentation.