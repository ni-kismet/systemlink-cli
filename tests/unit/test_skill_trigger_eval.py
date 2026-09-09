"""Unit tests for skill trigger evaluation semantics."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture(scope="module")
def run_eval_module() -> ModuleType:
    """Load the skill-creator trigger evaluator from its script directory."""
    script_dir = Path(".github/skills/skill-creator").resolve()
    cached_scripts = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "scripts" or name.startswith("scripts.")
    }
    sys.path.insert(0, str(script_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "skill_creator_run_eval", script_dir / "scripts" / "run_eval.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(script_dir))
        for name in list(sys.modules):
            if name == "scripts" or name.startswith("scripts."):
                sys.modules.pop(name)
        sys.modules.update(cached_scripts)


@pytest.mark.parametrize(
    ("item", "triggers", "positive_threshold", "negative_threshold", "expected"),
    [
        ({"query": "positive", "should_trigger": True}, [True, False], 0.5, 0.2, True),
        ({"query": "positive", "should_trigger": True}, [False, False], 0.5, 0.2, False),
        ({"query": "negative", "should_trigger": False}, [False] * 5, 0.8, 0.2, True),
        (
            {"query": "negative", "should_trigger": False},
            [True, False, False, False, False],
            0.8,
            0.2,
            False,
        ),
        ({"query": "fallback", "should_trigger": False}, [True, False], 0.5, None, False),
    ],
)
def test_summarize_query_result_thresholds(
    run_eval_module: ModuleType,
    item: dict[str, Any],
    triggers: list[bool],
    positive_threshold: float,
    negative_threshold: float | None,
    expected: bool,
) -> None:
    result = run_eval_module.summarize_query_result(
        item, triggers, 0, positive_threshold, negative_threshold
    )

    assert result["pass"] is expected
    assert result["status"] == ("pass" if expected else "fail")


def test_summarize_query_result_marks_executor_errors_inconclusive(
    run_eval_module: ModuleType,
) -> None:
    result = run_eval_module.summarize_query_result(
        {"query": "negative", "should_trigger": False}, [], 3, 0.8, 0.2
    )

    assert result["status"] == "inconclusive"
    assert result["pass"] is None
    assert result["trigger_rate"] is None
    assert result["errors"] == 3


def test_run_single_query_raises_for_nonzero_executor_exit(
    run_eval_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailedProcess:
        stdout = io.BytesIO()
        returncode = 2

        def poll(self) -> int:
            return 2

    monkeypatch.setattr(
        run_eval_module.subprocess, "Popen", lambda *args, **kwargs: FailedProcess()
    )

    with pytest.raises(run_eval_module.ExecutionError, match="exited with status 2"):
        run_eval_module.run_single_query("query", "skill", "description", 30, str(tmp_path))


def test_run_single_query_raises_for_timeout(
    run_eval_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class TimedOutProcess:
        stdout = io.BytesIO()
        returncode = None

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            self.returncode = -9

        def wait(self) -> None:
            return None

    timestamps = iter([0.0, 31.0])
    monkeypatch.setattr(
        run_eval_module.subprocess, "Popen", lambda *args, **kwargs: TimedOutProcess()
    )
    monkeypatch.setattr(run_eval_module.time, "time", lambda: next(timestamps))

    with pytest.raises(run_eval_module.ExecutionError, match="timed out after 30 seconds"):
        run_eval_module.run_single_query("query", "skill", "description", 30, str(tmp_path))


def test_require_conclusive_results_rejects_executor_errors(run_eval_module: ModuleType) -> None:
    with pytest.raises(RuntimeError, match="inconclusive for: failed query"):
        run_eval_module.require_conclusive_results(
            {
                "results": [
                    {
                        "query": "failed query",
                        "status": "inconclusive",
                        "pass": None,
                    }
                ]
            }
        )

    with pytest.raises(RuntimeError, match="inconclusive for: null result"):
        run_eval_module.require_conclusive_results(
            {"results": [{"query": "null result", "status": "unknown", "pass": None}]}
        )


def test_require_conclusive_results_accepts_passes_and_failures(
    run_eval_module: ModuleType,
) -> None:
    run_eval_module.require_conclusive_results(
        {
            "results": [
                {"query": "passed", "status": "pass", "pass": True},
                {"query": "failed", "status": "fail", "pass": False},
            ]
        }
    )


@pytest.mark.parametrize("value", ["-0.1", "1.1", "nan", "inf"])
def test_unit_interval_rate_rejects_invalid_values(run_eval_module: ModuleType, value: str) -> None:
    with pytest.raises(
        run_eval_module.argparse.ArgumentTypeError,
        match="finite value between 0 and 1",
    ):
        run_eval_module.unit_interval_rate(value)


@pytest.mark.parametrize("value", ["0", "0.5", "1"])
def test_unit_interval_rate_accepts_boundaries(run_eval_module: ModuleType, value: str) -> None:
    assert run_eval_module.unit_interval_rate(value) == float(value)
