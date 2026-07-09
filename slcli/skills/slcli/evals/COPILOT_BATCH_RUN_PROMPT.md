# Copilot Batch Eval Prompt

Use this prompt in a single parent Copilot Chat session when you want Copilot
to run the entire prepared `gating` iteration, populate the `outputs/`
folders, grade the results, aggregate the benchmark, and regenerate the static
review page.

This is the recommended orchestration pattern because the repo scripts handle
workspace preparation, grading, aggregation, and review rendering, but they do
not execute the model runs themselves.

Important: the parent chat is shared context. Do not execute both
`with_skill` and `without_skill` runs directly in the same running thread of
conversation if you want a meaningful baseline. Use fresh stateless subagents
per run so `without_skill` stays isolated from any prior skill-loaded context.

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
2. Read `orchestration_manifest.json` if it exists.
3. Find every `executor_prompt.txt` under the iteration directory if the orchestration manifest is missing.
4. For each prepared run directory:
   - execute the prompt in a fresh stateless subagent
   - load the `slcli` skill only for `with_skill` runs
   - do not load the `slcli` skill for `without_skill` runs
   - stop early when the per-run budget is exhausted and record the failure
   - save the final answer to `outputs/response.txt`
   - optionally save `outputs/notes.txt` for assumptions
5. Run `benchmark_iteration.py`.
6. Run `render_eval_review.py`.
7. Summarize which runs were populated and where the review HTML was written.

## Paste This Into Copilot Chat

```text
Run the prepared gating eval iteration end to end.

Use one parent conversation only as the orchestrator. For each executor prompt,
spawn a fresh stateless subagent so the runs do not share prompt history.
For `with_skill`, allow the subagent to read and use the skill at:
/Users/fvisser/Documents/GitRepositories/systemlink-cli/slcli/skills/slcli
For `without_skill`, explicitly do not load that skill.
Run independent evals in parallel when possible, but keep concurrency modest:
typically 2 to 4 subagents at a time.

Iteration workspace:
/Users/fvisser/Documents/GitRepositories/systemlink-cli/slcli/skills/slcli-workspace/iteration-1

Instructions:
1. Read iteration_manifest.json in that workspace.
2. Read orchestration_manifest.json in that workspace if it exists and use its max_parallel, max_tool_calls, max_minutes, and batches as the source of truth for scheduling.
3. If orchestration_manifest.json does not exist, discover every executor_prompt.txt under the iteration directory.
4. For each executor prompt:
   - execute the task described in the prompt in a fresh stateless subagent
   - use a maximum budget of about 8 tool calls or about 3 minutes of active work for that run, whichever comes first
   - if the run does not converge inside that budget, stop, write the best grounded response you have to response.txt, and write notes.txt explaining the failure briefly
   - save the final user-facing answer to the sibling outputs/response.txt path named in the prompt
   - save optional outputs/notes.txt only if assumptions or caveats matter
5. Do both configurations for every eval:
   - with_skill
   - without_skill
6. After all outputs are populated, run:
   - python slcli/skills/slcli/scripts/benchmark_iteration.py slcli/skills/slcli-workspace/iteration-1
   - python slcli/skills/slcli/scripts/render_eval_review.py slcli/skills/slcli-workspace/iteration-1
7. Report:
   - which run directories were populated
   - whether grading and benchmark generation succeeded
   - where review.html was written

Execution rules:
- Use the existing executor_prompt.txt files as the source of truth for each run.
- Do not answer multiple eval runs in the parent chat context.
- Do not reuse a subagent across runs.
- Parallelize independent runs when useful, but keep concurrency to roughly 2 to 4 subagents at a time.
- If orchestration_manifest.json is present, prefer its batch plan and concurrency limit over ad hoc scheduling.
- For with_skill runs, the subagent may read the skill path named in the executor prompt.
- For without_skill runs, the subagent must not load the skill and must rely only on repo code/context needed to answer the task.
- If a run exceeds its budget without a grounded answer, declare it failed quickly, persist the best grounded partial result plus a short note, and continue.
- Do not overwrite populated outputs unless the existing file is only a placeholder.
- Keep each response grounded in supported slcli commands and workflows.
- Save artifacts only inside the specified outputs/ directories.
- If a single run fails, continue with the remaining runs and report the failure at the end.
```

## Notes

- You do not need a new top-level chat for every eval. One parent chat can
  orchestrate the whole prepared gating suite if each run is delegated to a
  fresh stateless subagent.
- Yes, the subagents can be parallelized because the prepared runs are
   independent. Keep the batch size small so one bad run does not hide the rest.
- A plain single-thread conversation is not a clean `with_skill` versus
  `without_skill` comparison because the parent chat shares context across
  turns.
- You also do not need a repo script per eval. The intended split is:
  - repo scripts prepare, grade, aggregate, and render
  - Copilot orchestrates isolated subagent executions and writes the output
    artifacts
- If you want broader coverage, swap the iteration path to a prepared
  `regression` iteration.