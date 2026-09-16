# Copilot Batch Eval Prompt

Use this prompt in a single parent Copilot Chat session when you want Copilot
to run the entire prepared `gating` iteration, populate the `outputs/`
folders, grade the results, aggregate the benchmark, and regenerate the static
review page.

This is the recommended orchestration pattern because the repo scripts handle
workspace preparation, grading, aggregation, and review rendering, but they do
not execute the model runs themselves.

Important: the parent chat is shared context. Do not execute both
`with_skill` and `old_skill` runs directly in the same running thread of
conversation if you want a meaningful baseline. Use fresh stateless subagents
per run so the merge-base skill stays isolated from candidate context.

Also use a fail-fast budget per run. Do not let one struggling eval burn the
whole batch. A good default for the gating suite is a maximum of about 8 tool
calls or about 3 minutes of active work for a single run, whichever comes
first.

## When to use this

- You already created an iteration workspace with `prepare_eval_workspace.py`
- You already generated per-run `executor_prompt.txt` files with
  `prepare_eval_prompts.py`
- You want one parent Copilot chat to orchestrate all prepared gating evals end
  to end

## What this does

In one parent chat, Copilot should:

1. Read `iteration_manifest.json`.
2. Find every `executor_prompt.txt` under the iteration directory.
3. For each prepared run directory:
   - execute the prompt in a fresh stateless subagent

- load the candidate `slcli` skill from the run-specific candidate repo for `with_skill` runs
- load the merge-base `slcli` skill from the run-specific baseline repo for `old_skill` runs
- stop early when the per-run budget is exhausted and record the failure
- save the final answer to `outputs/response.txt`
- save the complete executor trace to `outputs/transcript.jsonl`
- have the parent orchestrator write normalized executor identity, configuration, and completion status to `outputs/run_metadata.json` from the iteration contract
- preserve any executor-authored identity or environment details separately in `outputs/executor_metadata_raw.json`
- save `total_tokens`, `duration_ms`, and derived `total_duration_seconds` from the subagent completion notification to the run's `timing.json`; do not estimate these values
- retry infrastructure failures once; after a second failure, set status to `infrastructure_error` and continue
- optionally save `outputs/notes.txt` for assumptions

For an iteration prepared with `--suite live_readonly` or `--suite online`, also do the following
for every live run:

- capture `fixture_snapshot_before.json` before the subagent starts;
- require `outputs/execution_records.json` with every `slcli` command, exit code,
  stdout, stderr, and parsed JSON output;
- capture `fixture_snapshot_after.json` after the subagent finishes;
- keep `fixture_snapshot.json` as the final readiness snapshot;
- treat `fixture_drift`, `unsupported`, and `inconclusive` readiness as
  capability-test evidence that is not an offline skill failure.

For `--suite online`, additionally follow the lifecycle assignment in each
run's `run_config.json`:

- local runs do not require remote fixture artifacts;
- before every remote run, invoke `fixture_lifecycle provision --run-dir` and
  require a `ready` lifecycle report;
- shared read-only runs must use the assigned fixture and must not mutate it;
- isolated runs must use only the assigned namespace and record every created
  resource in `outputs/created_resources.json`;
- after every remote run, invoke `fixture_lifecycle cleanup --run-dir`; for
  isolated runs it performs typed, ownership-checked deletes, and for shared
  runs it captures the final snapshot.

The lifecycle adapter validates an externally provisioned workspace. It does
not create a workspace implicitly, so the online fixture workspace must exist
before the batch starts.

Use `without_skill` as the baseline directory when the iteration was prepared
with `--baseline without_skill`; do not substitute `old_skill` for that
comparison.

4. Run `benchmark_iteration.py`.
5. Run `render_eval_review.py`.
6. Summarize which runs were populated and where the review HTML was written.

## Paste This Into Copilot Chat

```text
Run the prepared gating eval iteration end to end.

Use one parent conversation only as the orchestrator. For each executor prompt,
spawn a fresh stateless subagent so the runs do not share prompt history.
For `with_skill`, load the skill path inside the run-specific candidate repo
named by the executor prompt instead of using the working checkout.
For `old_skill`, load the skill path inside the run-specific baseline repo named
by the executor prompt instead of using the candidate checkout. Use only the
neutral input paths named by the executor prompt for attached fixtures.
Run independent evals in parallel when possible, but keep concurrency modest:
typically 2 to 4 subagents at a time.

Iteration workspace:
<ITERATION_DIR>

Instructions:
1. Read iteration_manifest.json in that workspace.
2. Discover every executor_prompt.txt under the iteration directory.
3. For each executor prompt:
   - execute the task described in the prompt in a fresh stateless subagent
   - use a maximum budget of about 8 tool calls or about 3 minutes of active work for that run, whichever comes first
   - if the run does not converge inside that budget, stop, write the best grounded response you have to response.txt, and write notes.txt explaining the failure briefly
   - save the final user-facing answer to the sibling outputs/response.txt path named in the prompt
  - save the complete executor trace to the sibling outputs/transcript.jsonl path named in the prompt
   - save optional outputs/notes.txt only if assumptions or caveats matter
  - as the parent orchestrator, save outputs/run_metadata.json using the provider, exact model, and harness from iteration_manifest.json plus the run-directory configuration and observed completion status
  - preserve model-authored identity or environment details separately in outputs/executor_metadata_raw.json when present
  - when the subagent completion notification arrives, immediately save its total_tokens and duration_ms plus derived total_duration_seconds to the sibling timing.json named in the executor prompt
  - use status `completed` only for a completed model run; retry an infrastructure failure once, then use `infrastructure_error` and preserve partial artifacts
4. Do both configurations for every eval:
   - with_skill
   - old_skill
5. After all outputs are populated, run:
  - poetry run python -m slcli.skills.slcli.scripts.benchmark_iteration <ITERATION_DIR>
  - poetry run python -m slcli.skills.slcli.scripts.render_eval_review <ITERATION_DIR>
6. Report:
   - which run directories were populated
   - whether grading and benchmark generation succeeded
   - where review.html was written

Execution rules:
- Use the existing executor_prompt.txt files as the source of truth for each run.
- Do not ask executor subagents to author run_metadata.json; normalized run identity belongs to the parent orchestrator.
- Do not answer multiple eval runs in the parent chat context.
- Do not reuse a subagent across runs.
- Parallelize independent runs when useful, but keep concurrency to roughly 2 to 4 subagents at a time.
- For with_skill runs, the subagent must load only the candidate skill path named in the executor prompt.
- For old_skill runs, the subagent must load only the merge-base skill path named in the executor prompt.
- If a run exceeds its budget without a grounded answer, declare it failed quickly, persist the best grounded partial result plus a short note, and continue.
- Do not overwrite populated outputs unless the existing file is only a placeholder.
- Keep each response grounded in supported slcli commands and workflows.
- Save response artifacts only inside the specified outputs/ directories; save timing.json at the run path named in the executor prompt.
- If a single run fails, continue with the remaining runs and report the failure at the end.
```

## Notes

- You do not need a new top-level chat for every eval. One parent chat can
  orchestrate the whole prepared gating suite if each run is delegated to a
  fresh stateless subagent.
- Yes, the subagents can be parallelized because the prepared runs are
  independent. Keep the batch size small so one bad run does not hide the rest.
- A plain single-thread conversation is not a clean `with_skill` versus
  `old_skill` comparison because the parent chat shares context across
  turns.
- You also do not need a repo script per eval. The intended split is:
  - repo scripts prepare, grade, aggregate, and render
  - Copilot orchestrates isolated subagent executions and writes the output
    artifacts
- If you want broader coverage, swap the iteration path to a prepared
  `regression` iteration.

Replace `<ITERATION_DIR>` with the prepared iteration path before using the
template.
