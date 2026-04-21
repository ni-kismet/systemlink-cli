---
name: slcli-pr-create
description: Create a concise GitHub pull request for the current changes. Ensures the work is on a feature branch, pushes it, and opens the PR.
argument-hint: Optional key=value args such as title="..." base=main draft=true context="..."
agent: agent
---

## Summary

Create and post a concise pull request for the current work. Before opening the PR, make sure the changes are on a non-default feature branch and pushed to GitHub.

## Arguments

Use `key=value` arguments. Quote values that contain spaces, for example `title="Add retry handling"` or `context="Call out follow-up work"`.

- `title` (optional): Preferred PR title, passed as `title="..."`
- `base` (optional): Target branch, passed as `base=main`. Default to the repository default branch.
- `draft` (optional): Create the PR as a draft when explicitly requested, passed as `draft=true` or `draft=false`.
- `context` (optional): Extra reviewer context to include in the PR description, passed as `context="..."`.

## Procedure

1. Inspect the git working tree, current branch, upstream status, and commits ahead of the base branch.
2. Summarize the planned git and PR operations for the user and ask for confirmation before creating a branch, committing, pushing, or opening the PR. Include the proposed branch name, commit message if needed, push target, base branch, and draft status.
3. If the current branch is the default branch, create a new descriptive feature branch and switch to it before proceeding.
4. If there are uncommitted changes, commit them with a concise commit message that matches the repo's commit style.
5. Push the branch to `origin` if it is not already published there.
6. Draft a concise PR title from the branch name, commits, and diff unless one was provided.
7. Draft a concise PR description with these sections:
   - `## Summary`
   - `## Testing`
   - `## Notes` only when needed for reviewer context
8. Open the PR on GitHub against the requested base branch or the repository default branch.
9. Report the branch name, commit range, PR number, and PR URL back to the user.

## Constraints

- Keep the PR title specific and under 72 characters when practical.
- Keep the PR description short and reviewer-oriented.
- Do not leave the changes on `main` or another shared protected branch.
- Do not create a draft PR unless the user asked for one or the branch is clearly not ready for review.

## Example

```bash
/slcli-pr-create
/slcli-pr-create title="Update semantic release changelog handling"
/slcli-pr-create base=release/1.x draft=true context="Include the Python Semantic Release v10 regression details"
```
