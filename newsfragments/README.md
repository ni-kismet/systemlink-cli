# Towncrier News Fragments

Every pull request must add at least one fragment in this directory.

Use a short branch-related stem as the fragment prefix and one of the configured types as the suffix:

- `major` for breaking changes
- `minor` for new features
- `patch` for fixes and behavior changes
- `doc` for documentation changes
- `misc` for other shipped changes

Choose a prefix that is specific to the change and easy to relate back to the branch or topic under review. PR- or issue-number prefixes are also accepted, but branch/topic stems are preferred for new fragments.

Examples:

```bash
poetry run towncrier create systems-search-fallback.patch.md --content "Prefer the new systems search endpoint with fallback."
poetry run towncrier create workitem-scheduling-helper.minor.md --content "Add a new workitem scheduling helper."
```

The release workflow uses these fragments to:

1. Determine the next package version.
2. Build the next `CHANGELOG.md` section.
3. Remove the consumed fragment files after the release commit is created.