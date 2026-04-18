---
name: slcli-pr-create
description: Create a concise GitHub pull request for the current changes. Ensures the work is on a feature branch, pushes it, and opens the PR.
argument-hint: Optional title, base branch, draft, or extra reviewer context
agent: agent
---

## Summary

Create and post a concise pull request for the current work. Before opening the PR, make sure the changes are on a non-default feature branch and pushed to GitHub.

## Arguments

- `title` (optional): Preferred PR title
- `base` (optional): Target branch. Default to the repository default branch.
- `draft` (optional): Create the PR as a draft when explicitly requested.
- `context` (optional): Extra reviewer context to include in the PR description.

## Procedure

1. Inspect the git working tree, current branch, upstream status, and commits ahead of the base branch.
2. If the current branch is the default branch, create a new descriptive feature branch and switch to it before proceeding.
3. If there are uncommitted changes, commit them with a concise commit message that matches the repo's commit style.
4. Push the branch to `origin` if it is not already published there.
5. Draft a concise PR title from the branch name, commits, and diff unless one was provided.
6. Draft a concise PR description with these sections:
   - `## Summary`
   - `## Testing`
   - `## Notes` only when needed for reviewer context
7. Open the PR on GitHub against the requested base branch or the repository default branch.
8. Report the branch name, commit range, PR number, and PR URL back to the user.

## Constraints

- Keep the PR title specific and under 72 characters when practical.
- Keep the PR description short and reviewer-oriented.
- Do not leave the changes on `main` or another shared protected branch.
- Do not create a draft PR unless the user asked for one or the branch is clearly not ready for review.

## Example

```bash
/slcli-pr-create
/slcli-pr-create Update semantic release changelog handling
/slcli-pr-create draft base=release/1.x include the Python Semantic Release v10 regression details
```
