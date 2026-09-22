# Skill Eval Regression Strategy

## Decision

Keep the branch's eval corpus, workspace layout, benchmark aggregation, and review UI as the
starting point. Do not use the current `with_skill` versus `without_skill` score as a regression
gate.

For an existing skill, the primary experiment must compare the candidate skill with the version
at the merge base. Both versions must run with the same model, agent harness, task, fixtures,
limits, and clean repository state. Grade observable outcomes first, use repeated trials to expose
nondeterminism, and retain the complete run evidence.

The repository should extend its existing Python harness instead of adopting another eval
framework now. The difficult part is producing controlled agent runs and trustworthy tasks and
graders, not calculating summary statistics. A provider-specific executor can be added behind a
small interface when a non-interactive Copilot runner is available.

## Branch Review

The branch provides a useful exploratory workflow:

- A versioned corpus with small `gating` and broader `regression` suites.
- Isolated run directories and optional baseline repository snapshots.
- Fresh subagents per trial to limit context leakage.
- Deterministic grading, aggregate reports, and a static review page.
- Fixtures for tasks that need file-backed context.

It does not yet establish that a skill change is non-regressing:

1. **The default comparison answers a different question.** The workflow defaults to
   `without_skill`, and the documentation asks whether the skill beats that baseline. That
   measures whether a skill is useful, not whether the edited skill is at least as reliable as
   the previous version. Although `old_skill` is an accepted directory name, the code does not
   create a merge-base skill snapshot.
2. **The grader can pass prose instead of behavior.** It concatenates every text-like output and
   searches independent regular expressions across the result. A response that quotes a valid
   command while advising against it can pass. Separate `all_of` matches can also occur in
   unrelated commands. File-producing tasks are not graded from filesystem state.
3. **One trial is treated as evidence.** `runs_per_config` defaults to one, despite agent output
   being nondeterministic. The aggregate script can calculate standard deviation but a single
   run always reports zero variance.
4. **Runs are not reproducible enough to compare.** The parent chat manually delegates work.
   Reports do not record the actual executor model, harness version, model settings, repository
   revisions, or full transcript. The benchmark currently contains model placeholders and a
   fixed claim of three runs per configuration.
5. **There is no regression decision.** Aggregation reports means and deltas but does not apply a
   non-inferiority threshold, identify candidate-only failures, or return a failing exit status.
6. **The harness itself has little behavioral coverage.** Current tests cover invalid UTF-8
   handling but not manifest validation, baseline construction, grading semantics, aggregation,
   or gate behavior. There are no positive and negative controls proving that each grader accepts
   a known-good answer and rejects known-bad answers.
7. **The corpus tests prompted execution, not skill routing.** Every candidate run is explicitly
   told to use the skill path. That is appropriate for testing the skill body, but it cannot catch
   a description change that causes the skill to under-trigger or over-trigger in normal use.

These limitations do not make the branch disposable. They mean it should be described as a local
benchmark and qualitative review workflow until the controls and gate below exist.

## Target Evaluation Model

Use three independent layers. A change can pass one layer and fail another, so report each layer
separately.

### 1. Harness and corpus tests

Run as ordinary deterministic unit tests on every pull request:

- Validate `evals.json` against a checked-in schema.
- Require stable IDs, known suite names, existing fixture paths, at least one grader per gating
  task, and an explicit `critical` flag for merge-blocking assertions.
- Run every grader against a checked-in positive control and at least one negative control.
- Test workspace isolation, merge-base snapshot construction, aggregation, and gate exit codes.
- Reject a task when its reference answer does not pass all critical deterministic graders.

This layer is cheap and should be required even when model credentials are unavailable.

### 2. Trigger tests

Test the skill frontmatter separately from task quality. Maintain balanced examples with
`should_trigger: true` and `should_trigger: false`, including near-boundary prompts and overlaps
with neighboring skills. Run each query at least five times and record the observed trigger rate.

Gate on both directions. For example, require positive trigger rate of at least 80% and negative
trigger rate below 20%. Explicitly injecting the skill is not a trigger test; the executor must
expose whether the production agent selected or read the skill.

If the available Copilot harness cannot emit that event non-interactively, keep this as a local or
scheduled test rather than inferring routing from the final answer.

### 3. Task outcome tests

For each task, execute paired trials against:

- `candidate`: the skill directory from the pull-request checkout.
- `baseline`: the complete skill directory from `git merge-base origin/main HEAD`.

Use a fresh temporary repository copy for every trial. Remove prior outputs, caches, conversation
history, and generated files. Candidate and baseline must use the same executor model and version,
agent harness version, permissions, tool set, budgets, environment, and fixture content. Alternate
execution order to reduce time-correlated bias.

Prefer graders in this order:

1. **End-state checks:** inspect generated files, parsed JSON, command exit status, or sandbox
   state. For coding tasks, run the relevant tests.
2. **Structured command checks:** extract fenced `slcli` commands, parse each command, and validate
   the command path, options, and relationships within the same invocation. Do not search all
   prose for disconnected tokens.
3. **Transcript checks:** verify required tool use only when the path itself is part of the
   contract. Usually the outcome matters more than an exact tool sequence.
4. **Model graders:** use narrow rubrics for qualities that cannot be tested in code, such as
   clarity or whether an explanation addresses the request. Give the grader an `unknown` result,
   keep each rubric dimension separate, and calibrate it against human labels before making it
   merge-blocking.

Each task should support partial credit for diagnostics while identifying critical assertions
that must pass. A critical safety or correctness failure cannot be averaged away by stylistic
successes.

## Trial Counts and Gate Semantics

Use different budgets for different feedback loops:

| Suite      | When                | Trials per version | Purpose                                  | Merge blocking         |
| ---------- | ------------------- | -----------------: | ---------------------------------------- | ---------------------- |
| Harness    | Every relevant PR   |                  1 | Validate corpus and grader code          | Yes                    |
| Smoke      | Local development   |                  1 | Fast feedback while editing              | No                     |
| Gating     | Skill-changing PR   |                  3 | Paired candidate versus merge-base check | Yes, after calibration |
| Regression | Nightly and release |                  5 | Reliability, variance, and model drift   | Release blocking       |

For the PR gate:

- Fail if the candidate introduces a critical deterministic failure on a task where the baseline
  passes at least two of three paired trials.
- Fail if candidate mean assertion pass rate is more than 5 percentage points below baseline.
- Report, but initially do not fail on, latency, token use, or model-graded quality deltas.
- Classify infrastructure errors separately from task failures. Retry an infrastructure error
  once; an unresolved error makes the run inconclusive, not a model failure.
- When a task changes in the same pull request as the skill, require human review of that task and
  exclude it from old-versus-new gating until its positive and negative controls pass. This avoids
  moving the goalposts while evaluating the candidate.

After enough runs have accumulated, replace the simple aggregate threshold with a paired bootstrap
confidence interval over task-trial scores. Keep the candidate when the lower bound of
`candidate - baseline` is above the agreed non-inferiority margin. Do not claim statistical
confidence from the current five-task, one-trial gating run.

For reliability reporting, show per-task success rate and `pass^k`, the estimated probability that
all `k` attempts succeed. A skill used interactively should be reliable on the first attempt; a
best-of-many `pass@k` score can hide that regression.

## Corpus Design

Evolve the current eleven examples into a maintained test bank:

- Start with real user workflows, fixed bugs, support cases, and ambiguous requests seen in use.
- Include positive, negative, boundary, and failure-recovery cases for each important behavior.
- Give every task an unambiguous prompt, a known-good reference result, critical assertions, and
  named noncritical dimensions.
- Keep a small holdout suite unavailable to routine prompt tuning. Run it nightly or before a
  release to detect overfitting to the visible gating cases.
- Add every confirmed production or review regression as a new task with a negative control.
- Version the corpus and graders independently from the skill. Store the corpus hash in each run.
- Periodically inspect transcripts and candidate-only failures. A score is not trustworthy until
  reviewers confirm that failures are fair and passing runs actually solved the task.

The current command-oriented cases should gain structured command controls. For example, the
grader for a filtered result query should parse one recommended invocation and verify that the
same invocation contains the expected command group, product constraint, status constraint, and
JSON format. A warning that merely mentions an unsupported command must not trigger a failure.

## Run Record

Write one machine-readable record per trial containing:

- skill name, candidate SHA, merge-base SHA, and hashes of both skill directories
- corpus and grader versions or hashes
- executor provider, exact model identifier, harness version, model settings, and seed when
  supported
- task ID, trial number, configuration, start time, duration, tokens, tool calls, and errors
- complete transcript or provider trace, final response, and produced-file manifest with hashes
- each grader result with score, evidence, grader type, and grader version
- final classification: `pass`, `fail`, or `inconclusive`

Upload the JSON results, transcripts, output files, benchmark Markdown, and static review page as
CI artifacts. Do not commit routine run output. A pull-request summary should show baseline and
candidate scores, paired deltas, candidate-only failures, inconclusive trials, and artifact links.

## Implementation Plan

### Phase 1: Make the local comparison valid

1. Change the default baseline for an existing skill to `old_skill`.
2. Add `--baseline-ref`, defaulting to the merge base with `origin/main`, and materialize the old
   skill with Git rather than copying the candidate checkout and deleting the skill.
3. Default gating runs to three trials per configuration.
4. Record real run metadata and fail when prepared runs or required metadata are missing.
5. Add a `compare_iteration.py` command that applies the gate semantics and exits nonzero on a
   regression.

### Phase 2: Make grading trustworthy

1. Define a manifest schema and a Python grader protocol that receives the task, transcript,
   response, and sandbox path.
2. Replace broad response regexes with command-aware and end-state graders.
3. Add reference answers plus negative controls and test all graders in `tests/unit/`.
4. Retain regexes only for narrow presentation checks where text presence is truly the outcome.
5. Add optional model-rubric graders only after a small human-labeled calibration set exists.

### Phase 3: Automate without hiding variance

1. Introduce an executor adapter that returns a normalized transcript and metadata. Keep Copilot-
   specific invocation outside corpus and grading code.
2. Add a path-filtered GitHub Actions workflow for skill, eval, or harness changes. Always run
   deterministic harness tests; run model trials only when credentials and a supported
   non-interactive executor are available.
3. Upload all run artifacts and publish a concise pull-request summary.
4. Start the stochastic check as advisory. Make it required only after several weeks of measuring
   false alarms, infrastructure failures, cost, and runtime.
5. Run the larger holdout regression suite nightly and on releases to detect model or harness
   drift even when repository files did not change.

## Acceptance Criteria

The workflow is ready to be called a regression gate when all of the following are true:

- A local command can compare any skill change against its merge-base version without manual
  file preparation.
- Candidate and baseline run through the same recorded executor configuration in clean sandboxes.
- Gating uses at least three paired trials and reports variance and candidate-only failures.
- Every critical grader has passing and failing controls, and file-producing tasks inspect final
  state.
- The comparison command returns a documented nonzero exit code for a regression.
- Trigger tests include both should-trigger and should-not-trigger examples.
- A reviewer can inspect complete traces and outputs for every failed or inconclusive trial.
- CI runs deterministic validation on every relevant pull request and retains eval artifacts.

## Sources

- Anthropic, [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), January 9, 2026. Defines tasks, trials, graders, transcripts, and outcomes; recommends multiple trials, clean isolated environments, outcome-first deterministic grading, balanced datasets, reference solutions, transcript review, and separate capability and regression suites.
- OpenAI, [Working with evals](https://developers.openai.com/api/docs/guides/evals). Documents schema-defined datasets, human ground truth, explicit testing criteria, per-criterion results, usage metadata, and report artifacts. The page also announces that the hosted Evals platform is scheduled to shut down on November 30, 2026, so this proposal does not make it a repository dependency.
- OpenAI Cookbook, [Detecting prompt regressions](https://developers.openai.com/cookbook/examples/evaluation/use-cases/regression). Demonstrates running a stable dataset and grader against baseline and changed prompts and comparing the resulting runs.
- Promptfoo, [Assertions and metrics](https://www.promptfoo.dev/docs/configuration/expected-outputs/). Documents deterministic, custom-code, trajectory, model-assisted, weighted, and thresholded graders.
- Promptfoo, [CI/CD integration](https://www.promptfoo.dev/docs/integrations/ci-cd/). Documents path-filtered CI, machine-readable and HTML/JUnit output, quality gates, artifacts, run tags, and cache controls.
- Repository-local [skill-creator guidance](../.github/skills/skill-creator/SKILL.md). Already prescribes old-skill snapshots for existing-skill improvements, simultaneous baseline and candidate runs, timing capture, multiple runs, qualitative review, and transcript analysis.
