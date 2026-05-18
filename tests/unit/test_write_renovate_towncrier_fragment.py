"""Tests for Renovate Towncrier fragment generation."""

import json
from pathlib import Path

import pytest
from scripts.write_renovate_towncrier_fragment import (
    build_fragment_content,
    build_fragment_content_from_title,
    main,
    parse_args,
    sanitize_fragment_stem,
    write_fragment,
    write_title_fragment,
)


def test_sanitize_fragment_stem_normalizes_branch_topic() -> None:
    """Branch topics should become stable, filesystem-safe stems."""
    assert sanitize_fragment_stem("Python Runtime Dependencies") == "python-runtime-dependencies"
    assert sanitize_fragment_stem("renovate/github-actions") == "renovate-github-actions"
    assert sanitize_fragment_stem("!!!") == "dependencies"


def test_build_fragment_content_summarizes_grouped_updates() -> None:
    """Grouped updates should produce a concise summary sentence."""
    content = build_fragment_content(
        [
            {"depName": "click", "newValue": "8.1.8"},
            {"depName": "rich", "newValue": "14.1.0"},
            {"depName": "requests", "newValue": "2.32.4"},
            {"depName": "urllib3", "newValue": "2.5.0"},
        ]
    )

    assert content == (
        "Update dependencies click to 8.1.8, rich to 14.1.0, requests to 2.32.4, and 1 other"
    )


def test_build_fragment_content_from_title_normalizes_dependency_pr_title() -> None:
    """Dependency PR titles should become valid fragment text."""
    assert (
        build_fragment_content_from_title(
            "chore(deps): Update dependency python-multipart to v0.0.29"
        )
        == "Update dependency python-multipart to v0.0.29."
    )


def test_build_fragment_content_from_title_handles_empty_title() -> None:
    """Empty dependency PR titles should still produce a punctuated fragment."""
    assert build_fragment_content_from_title("   ") == "Update dependencies."


def test_write_fragment_creates_deterministic_patch_file(tmp_path: Path) -> None:
    """The helper should write a patch fragment under newsfragments/."""
    repo_root = tmp_path
    (repo_root / "newsfragments").mkdir()

    data_file = repo_root / "upgrades.json"
    data_file.write_text(
        json.dumps([{"depName": "rich", "newValue": "15.0.0"}]),
        encoding="utf-8",
    )

    fragment_path = write_fragment(data_file, "python-runtime-dependencies", repo_root)

    assert (
        fragment_path == repo_root / "newsfragments" / "deps-python-runtime-dependencies.patch.md"
    )
    assert fragment_path.read_text(encoding="utf-8") == "Update dependency rich to 15.0.0\n"


def test_write_title_fragment_creates_deterministic_patch_file(tmp_path: Path) -> None:
    """PR-title fallback should write the same deterministic patch file pattern."""
    repo_root = tmp_path
    (repo_root / "newsfragments").mkdir()

    fragment_path = write_title_fragment(
        "chore(deps): Update dependency python-multipart to v0.0.29",
        "python-multipart-0.x-lockfile",
        repo_root,
    )

    assert (
        fragment_path == repo_root / "newsfragments" / "deps-python-multipart-0-x-lockfile.patch.md"
    )
    assert (
        fragment_path.read_text(encoding="utf-8")
        == "Update dependency python-multipart to v0.0.29.\n"
    )


def test_parse_args_accepts_data_file_and_branch_topic() -> None:
    """CLI should preserve the existing Renovate invocation order."""
    args = parse_args(["upgrades.json", "python-runtime-dependencies"])

    assert args.data_file == Path("upgrades.json")
    assert args.branch_topic == "python-runtime-dependencies"
    assert args.pr_title is None


def test_parse_args_accepts_pr_title_without_data_file() -> None:
    """CLI should accept PR-title fallback mode with only a branch topic."""
    args = parse_args(["--pr-title", "chore(deps): Update rich", "python-runtime-dependencies"])

    assert args.data_file is None
    assert args.branch_topic == "python-runtime-dependencies"
    assert args.pr_title == "chore(deps): Update rich"


def test_parse_args_requires_branch_topic_without_pr_title() -> None:
    """CLI should reject data-file mode when branch topic is missing."""
    with pytest.raises(SystemExit):
        parse_args(["upgrades.json"])


def test_main_writes_title_fragment_and_prints_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI entrypoint should write a fragment in PR-title fallback mode."""
    (tmp_path / "newsfragments").mkdir()

    exit_code = main(
        [
            "--pr-title",
            "chore(deps): Update dependency python-multipart to v0.0.29",
            "python-multipart-0.x-lockfile",
            "--repo-root",
            str(tmp_path),
        ]
    )

    fragment_path = tmp_path / "newsfragments" / "deps-python-multipart-0-x-lockfile.patch.md"
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == str(fragment_path)
    assert (
        fragment_path.read_text(encoding="utf-8")
        == "Update dependency python-multipart to v0.0.29.\n"
    )
