"""Generate a Towncrier fragment for Renovate update branches."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

MAX_LISTED_UPGRADES = 3


def sanitize_fragment_stem(branch_topic: str) -> str:
    """Convert a Renovate branch topic into a stable fragment stem.

    Args:
        branch_topic: The branch topic supplied by Renovate.

    Returns:
        A filesystem-safe fragment stem.
    """
    sanitized = re.sub(r"[^a-z0-9]+", "-", branch_topic.lower()).strip("-")
    return sanitized or "dependencies"


def _join_entries(entries: Sequence[str]) -> str:
    """Join dependency entries into a natural-language list.

    Args:
        entries: Dependency update entries.

    Returns:
        A human-readable list string.
    """
    if len(entries) == 1:
        return entries[0]
    if len(entries) == 2:
        return f"{entries[0]} and {entries[1]}"
    return f"{', '.join(entries[:-1])}, and {entries[-1]}"


def build_fragment_content(upgrades: Sequence[Mapping[str, Any]]) -> str:
    """Build fragment content from Renovate upgrade metadata.

    Args:
        upgrades: Upgrade objects from Renovate's data file.

    Returns:
        A concise Towncrier fragment sentence.
    """
    entries: list[str] = []
    seen_entries: set[str] = set()

    for upgrade in upgrades:
        dep_name = str(upgrade.get("depName", "")).strip()
        new_value = str(upgrade.get("newValue", "")).strip()
        if not dep_name:
            continue

        entry = dep_name if not new_value else f"{dep_name} to {new_value}"
        if entry in seen_entries:
            continue

        seen_entries.add(entry)
        entries.append(entry)

    if not entries:
        return "Update dependencies"

    if len(entries) == 1:
        return f"Update dependency {entries[0]}"

    if len(entries) <= MAX_LISTED_UPGRADES:
        return f"Update dependencies {_join_entries(entries)}"

    listed_entries = entries[:MAX_LISTED_UPGRADES]
    remaining = len(entries) - MAX_LISTED_UPGRADES
    other_label = "other" if remaining == 1 else "others"
    return f"Update dependencies {', '.join(listed_entries)}, and {remaining} {other_label}"


def load_upgrades(data_file: Path) -> list[dict[str, Any]]:
    """Load upgrade metadata written by Renovate.

    Args:
        data_file: Path to Renovate's JSON data file.

    Returns:
        Parsed upgrade objects.
    """
    with data_file.open(encoding="utf-8") as handle:
        raw_data = json.load(handle)

    if not isinstance(raw_data, list):
        raise ValueError("Expected Renovate post-upgrade data to be a JSON array")

    return [item for item in raw_data if isinstance(item, dict)]


def write_fragment(data_file: Path, branch_topic: str, repo_root: Path) -> Path:
    """Write the generated fragment into newsfragments/.

    Args:
        data_file: Path to Renovate's JSON data file.
        branch_topic: Renovate branch topic used for deterministic naming.
        repo_root: Repository root directory.

    Returns:
        The path to the generated fragment.
    """
    upgrades = load_upgrades(data_file)
    content = build_fragment_content(upgrades)

    fragment_name = f"deps-{sanitize_fragment_stem(branch_topic)}.patch.md"
    fragment_path = repo_root / "newsfragments" / fragment_name
    fragment_path.write_text(f"{content}\n", encoding="utf-8")
    return fragment_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_file", type=Path)
    parser.add_argument("branch_topic")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a deterministic Towncrier fragment for a Renovate branch.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit code.
    """
    args = parse_args(argv)
    fragment_path = write_fragment(args.data_file, args.branch_topic, args.repo_root)
    print(fragment_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
