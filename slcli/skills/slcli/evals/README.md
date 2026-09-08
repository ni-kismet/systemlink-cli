# slcli Eval Workflow

This directory contains the eval corpus for the repo-local `slcli` skill.
Use the `gating` suite to compare a candidate skill with its merge-base version
after a skill edit. The default is three paired trials per configuration.

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
- generate executor prompts
- execute `with_skill` and `old_skill` runs via isolated subagents
- grade and aggregate the iteration
- apply the regression gate
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

The iteration contains paired candidate and baseline repository templates from
the current candidate checkout. Only the `slcli` skill in the baseline template
is replaced with its version from the merge base of `origin/main` and `HEAD`.
Each trial receives its own copy of the appropriate template, so parallel runs
cannot modify another trial's repository. File-backed fixtures are copied into
a neutral `inputs/` directory shared by both arms. Use
`--baseline-ref` when comparing against another branch. Use
`--baseline without_skill --isolate-baseline` only when measuring whether a new
skill adds value; that comparison is not a regression test.

#### Generate executor prompts

```bash
python slcli/skills/slcli/scripts/prepare_eval_prompts.py \
  slcli/skills/slcli-workspace/iteration-1 \
  --max-tool-calls 8 \
  --max-minutes 3
```

This writes one `executor_prompt.txt` per prepared run.

#### Execute the runs in Copilot

Use [COPILOT_BATCH_RUN_PROMPT.md](./COPILOT_BATCH_RUN_PROMPT.md) together with
the generated `executor_prompt.txt` files.

Recommended execution pattern:

1. Use one parent chat as the orchestrator.
2. Run each prepared eval in a fresh stateless subagent.
3. Point `with_skill` runs at the run-specific candidate skill path in its prompt.
4. Point `old_skill` runs at the run-specific baseline skill path in its prompt.
5. Keep concurrency modest, usually 2 to 4 runs at a time.
6. If a run exceeds its budget, save the best grounded `response.txt`, add a short `notes.txt`, and continue.

Each run saves artifacts under its own `outputs/` directory. Every run must
write:

- `response.txt`: final user-facing response
- `transcript.jsonl`: complete executor trace for audit and diagnosis
- `run_metadata.json`: `executor_provider`, exact `executor_model`, `harness`,
  `configuration`, and `status` (`completed` or `infrastructure_error`)

Candidate and baseline trials are incomparable when provider, model, or harness
metadata differs.

The gate also treats a run as inconclusive when its candidate/baseline hashes,
eval manifest hash, run identity, classification, or detailed grading payload
does not match the immutable provenance captured in `run_record.json`.

Retry an infrastructure failure once. If the retry also fails, preserve the
partial artifacts with `status: infrastructure_error`; the gate reports that
trial as inconclusive instead of scoring it as a skill failure.

## Harness Invariants

- Every trial uses a fresh repository sandbox and a fresh stateless subagent.
- Candidate and baseline sandboxes begin from the same candidate repository;
  only the baseline skill directory differs.
- Input fixtures live outside both skill trees and are identical for both arms.
- Copied fixture hashes must match their preparation-time input manifest.
- Critical compound workflows must pass within one command invocation.
- Positive controls must use supported command paths and required arguments.
- Executor errors and provenance mismatches are inconclusive, never passing evidence.

#### Grade and aggregate the iteration

```bash
python slcli/skills/slcli/scripts/benchmark_iteration.py --force \
  slcli/skills/slcli-workspace/iteration-1
```

This grades populated runs, writes `run_record.json` per trial, generates
`benchmark.json` plus `benchmark.md`, and applies the regression gate. It also
writes `regression.json` and `regression.md`.

The gate exits with:

- `0`: no detected regression
- `1`: regression detected
- `2`: inconclusive because runs or required metadata are missing or incompatible

The default gate fails when the baseline passes the critical rules in a
majority of trials and any paired candidate trial introduces a critical
failure. It also fails when mean assertion pass rate drops by more than five
percentage points.

#### Regenerate the review page

```bash
python slcli/skills/slcli/scripts/render_eval_review.py \
  slcli/skills/slcli-workspace/iteration-1
```

This writes `review.html` in the iteration directory.

## What Good Looks Like

- `with_skill` should be non-inferior to `old_skill` on the gating suite.
- Failures should point to missing skill behavior, not to ambiguous eval wording.
- If both configs pass easily, keep the case for regression coverage and add
  harder cases to a separate capability suite.
- If both configs fail, tighten the prompt or grading rules before changing the skill.

## Files in This Directory

- `evals.json`: prompts, fixtures, and grading rules
- `evals.schema.json`: machine-readable corpus contract
- `trigger_evals.json`: balanced should-trigger and should-not-trigger prompts
- `files/`: input fixtures for file-backed evals
- `../../../../.github/prompts/eval-skill-gating.prompt.md`: one-shot gating eval prompt
- `COPILOT_BATCH_RUN_PROMPT.md`: parent-chat orchestration prompt
- `../scripts/prepare_eval_workspace.py`: scaffolds an iteration directory
- `../scripts/prepare_eval_prompts.py`: writes executor prompts
- `../scripts/benchmark_iteration.py`: grades and aggregates a full iteration
- `../scripts/render_eval_review.py`: writes the static review page

## Broader Coverage

Use `regression` with five trials before a release:

```bash
python slcli/skills/slcli/scripts/prepare_eval_workspace.py \
  --suite regression \
  --runs-per-config 5
```

## Trigger Evaluation

Trigger evaluation is separate from task execution because task prompts inject
the skill explicitly. When the Claude CLI is available, run the repository's
trigger evaluator with balanced thresholds:

```bash
python .github/skills/skill-creator/scripts/run_eval.py \
  --eval-set slcli/skills/slcli/evals/trigger_evals.json \
  --skill-path slcli/skills/slcli \
  --runs-per-query 5 \
  --trigger-threshold 0.8 \
  --negative-trigger-threshold 0.2
```

This is a local or scheduled check until the production Copilot harness exposes
skill-selection events through a non-interactive executor. Do not infer routing
from final-answer text.

## CI Coverage

The existing CI workflow runs the deterministic manifest, grader, snapshot,
and comparator unit tests on every pull request. Model trials remain an
explicit developer workflow because this repository does not yet have a
credentialed non-interactive Copilot executor. Attach `benchmark.json`,
`regression.json`, `review.html`, run records, transcripts, and outputs to a PR
when reviewing a skill change.

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
