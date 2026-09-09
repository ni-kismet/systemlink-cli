"""Unit tests for benchmark metadata enrichment."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

from slcli.skills.slcli.scripts.benchmark_iteration import enrich_benchmark


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_enrich_benchmark_uses_candidate_delta_and_updates_markdown(tmp_path: Path) -> None:
    write_json(
        tmp_path / "benchmark.json",
        {
            "metadata": {
                "skill_name": "slcli",
                "timestamp": "2026-09-08T00:00:00Z",
                "evals_run": [1],
            },
            "run_summary": {
                "old_skill": {
                    "pass_rate": {"mean": 0.5},
                    "time_seconds": {"mean": 2.0},
                    "tokens": {"mean": 100},
                },
                "with_skill": {
                    "pass_rate": {"mean": 0.75},
                    "time_seconds": {"mean": 3.0},
                    "tokens": {"mean": 120},
                },
                "delta": {"pass_rate": "-0.25", "time_seconds": "-1.0", "tokens": "-20"},
            },
        },
    )
    write_json(
        tmp_path / "iteration_manifest.json",
        {
            "baseline": "old_skill",
            "runs_per_config": 5,
            "candidate_sha": "candidate",
            "baseline_sha": "baseline",
            "candidate_skill_hash": "candidate-hash",
            "baseline_skill_hash": "baseline-hash",
            "eval_manifest_hash": "manifest-hash",
        },
    )
    write_json(
        tmp_path / "eval-1" / "with_skill" / "run-1" / "outputs" / "run_metadata.json",
        {
            "executor_model": "test-model",
            "executor_provider": "test-provider",
            "harness": "test-harness",
        },
    )
    aggregate_script = Path(".github/skills/skill-creator/scripts/aggregate_benchmark.py")

    enrich_benchmark(tmp_path, aggregate_script)

    benchmark = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert benchmark["run_summary"]["delta"]["pass_rate"] == "+0.25"
    markdown = (tmp_path / "benchmark.md").read_text(encoding="utf-8")
    assert "**Model**: test-model" in markdown
    assert "(5 runs each per configuration)" in markdown
    assert "| Pass Rate | 50%" in markdown
    assert "| 75%" in markdown
    assert "| +0.25 |" in markdown


@pytest.mark.parametrize("metadata_content", ["{", "[]", '{"executor_model": null}'])
def test_enrich_benchmark_ignores_invalid_executor_metadata(
    tmp_path: Path, metadata_content: str
) -> None:
    write_json(
        tmp_path / "benchmark.json",
        {
            "metadata": {
                "skill_name": "slcli",
                "timestamp": "2026-09-08T00:00:00Z",
                "evals_run": [1],
            },
            "run_summary": {"with_skill": {}, "old_skill": {}},
        },
    )
    write_json(
        tmp_path / "iteration_manifest.json",
        {"baseline": "old_skill", "runs_per_config": 1},
    )
    metadata_path = tmp_path / "eval-1" / "with_skill" / "run-1" / "outputs" / "run_metadata.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(metadata_content, encoding="utf-8")

    enrich_benchmark(tmp_path, Path(".github/skills/skill-creator/scripts/aggregate_benchmark.py"))

    benchmark = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert benchmark["metadata"]["executor_model"] == "unknown"
    assert benchmark["metadata"]["executor_provider"] == "unknown"
    assert benchmark["metadata"]["executor_harness"] == "unknown"


def test_aggregate_skips_inconclusive_grading(tmp_path: Path) -> None:
    grading_path = tmp_path / "eval-1" / "with_skill" / "run-1" / "grading.json"
    write_json(
        grading_path,
        {
            "classification": "inconclusive",
            "summary": {"pass_rate": 1.0, "passed": 1, "failed": 0, "total": 1},
        },
    )
    aggregate_module = runpy.run_path(".github/skills/skill-creator/scripts/aggregate_benchmark.py")

    results = aggregate_module["load_run_results"](tmp_path)

    assert results == {"with_skill": []}


def test_aggregate_uses_measured_tokens_instead_of_output_characters(tmp_path: Path) -> None:
    grading_path = tmp_path / "eval-1" / "with_skill" / "run-1" / "grading.json"
    write_json(
        grading_path,
        {
            "classification": "pass",
            "summary": {"pass_rate": 1.0, "passed": 1, "failed": 0, "total": 1},
            "timing": {"total_duration_seconds": 2.5},
            "execution_metrics": {"total_tokens": 42, "output_chars": 1000},
            "expectations": [],
        },
    )
    aggregate_module = runpy.run_path(".github/skills/skill-creator/scripts/aggregate_benchmark.py")

    results = aggregate_module["load_run_results"](tmp_path)

    assert results["with_skill"][0]["tokens"] == 42
    assert results["with_skill"][0]["time_seconds"] == 2.5
