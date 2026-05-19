---
name: slcli-pr-create
description: Create a concise GitHub pull request for the current changes. Ensures the work is on a feature branch, pushes it, and opens the PR.
argument-hint: Optional key=value args such as title="..." base=main draft=true context="..."
agent: agent
---

## Summary

Create and post a concise, high-quality pull request for the current work. Detect whether the changes are already on a non-default feature branch and reuse it; if the work is still on the default branch, create a new descriptive feature branch automatically. Ensure any required Towncrier newsfragment entries under `newsfragments/` exist, review the changes before posting, run the required validation, push the branch, open the PR, and prefer to finish only when the PR build pipeline is green.

## Arguments

Use `key=value` arguments. Quote values that contain spaces, for example `title="Add retry handling"` or `context="Call out follow-up work"`.

- `title` (optional): Preferred PR title, passed as `title="..."`
- `base` (optional): Target branch, passed as `base=main`. Default to the repository default branch.
- `draft` (optional): Create the PR as a draft when explicitly requested, passed as `draft=true` or `draft=false`.
- `context` (optional): Extra reviewer context to include in the PR description, passed as `context="..."`.

## Procedure

1. Inspect the git working tree, current branch, upstream status, and commits ahead of the base branch.
2. Detect whether the work is already on a non-default branch. If so, reuse that branch. If the work is still on the default branch, create and switch to a new descriptive feature branch automatically before proceeding.
3. Check whether the branch includes the required Towncrier newsfragment(s) under `newsfragments/` for the proposed changes. If a valid fragment is missing, create one automatically using a short branch-related stem plus one of the configured types (`major`, `minor`, `patch`, `doc`, `misc`).
4. Review the current diff before committing. Look for obvious bugs, missing tests, missing release notes, weak PR framing, or gaps against repo instructions, and make small follow-up fixes when needed so the PR is reviewable and high quality.
5. Run the repo's required validation flow before opening the PR. Prefer the project-standard sequence for linting, type checking, unit tests, and the full test suite. If a failure is caused by the current changes, fix it and rerun. If a failure is pre-existing on the base branch, confirm that and carry it forward transparently in the PR notes instead of widening scope unnecessarily.
6. If there are uncommitted changes, commit them with a concise commit message that matches the repo's commit style.
7. Push the branch to `origin` if it is not already published there.
8. Draft a concise PR title from the branch name, commits, and diff unless one was provided.
9. Draft a concise PR description with these sections:
   - `## Summary`
   - `## Testing`
   - `## Release Notes` when a Towncrier fragment was added or updated, summarizing the fragment type and intent in one line
   - `## Notes` only when needed for reviewer context
10. Open the PR on GitHub against the requested base branch or the repository default branch.
11. When tooling is available, check the PR status checks after opening it and continue fixing branch-caused failures until the pipeline is green. If status checks are unavailable, still post the PR but call out that pipeline state could not be verified. If checks fail for reasons unrelated to the branch changes or due to external infrastructure, report that explicitly.
12. Report the branch name, commit range, PR number, PR URL, Towncrier fragment file(s), and validation/check status back to the user.

## Constraints

- Keep the PR title specific and under 72 characters when practical.
- Keep the PR description short and reviewer-oriented.
- Do not leave the changes on `main` or another shared protected branch.
- If already on a suitable non-default branch, do not create a second branch.
- Do not create a draft PR unless the user asked for one or the branch is clearly not ready for review.
- Do not open the PR without the required committed Towncrier fragment(s); create or update the fragment automatically when the change warrants it.
- Remember that `poetry run towncrier check --compare-with origin/main` only sees committed branch contents, so an untracked fragment does not satisfy the requirement.
- Do not stop for a confirmation step once the user has invoked this prompt; execute the branch, Towncrier, review, validation, push, and PR workflow autonomously.
- Prefer to finish with a PR whose build pipeline is green. If that cannot be achieved because of unrelated existing failures, unavailable status-check tooling, or external CI issues, explain the blocker precisely in the final report.

## Example

```bash
/slcli-pr-create
/slcli-pr-create title="Update semantic release changelog handling"
/slcli-pr-create base=release/1.x draft=true context="Include the Python Semantic Release v10 regression details"
```
