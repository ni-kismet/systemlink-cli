"""Unit tests for the checked-in skill eval manifest."""

import json
from datetime import date
from pathlib import Path

import pytest

from slcli.skills.slcli.scripts.eval_manifest import load_manifest, validate_manifest
from slcli.skills.slcli.scripts.grade_eval_response import evaluate_rule
from slcli.webapp_click import _validate_plugin_manager_metadata


def test_checked_in_eval_manifest_is_valid() -> None:
    manifest = Path("slcli/skills/slcli/evals/evals.json")

    payload = load_manifest(manifest)

    assert payload["manifest_version"] == 1


def test_manifest_requires_explicit_critical_flags(tmp_path: Path) -> None:
    payload = {
        "manifest_version": 1,
        "skill_name": "test",
        "recommended_suites": {"gating": [1], "regression": [1]},
        "evals": [
            {
                "id": 1,
                "prompt": "test",
                "expected_output": "test",
                "files": [],
                "expectations": ["test"],
                "grading_rules": [{"text": "rule", "mode": "any_of", "patterns": ["expected"]}],
            }
        ],
    }

    with pytest.raises(ValueError, match="explicit critical flag"):
        validate_manifest(payload, tmp_path)


def test_manifest_requires_schema_entry_fields(tmp_path: Path) -> None:
    payload = {
        "manifest_version": 1,
        "skill_name": "test",
        "recommended_suites": {"gating": [1], "regression": [1]},
        "evals": [
            {
                "id": 1,
                "prompt": "test",
                "expected_output": "test",
                "grading_rules": [],
            }
        ],
    }

    with pytest.raises(ValueError, match="missing required fields"):
        validate_manifest(payload, tmp_path)


@pytest.mark.parametrize(
    "fixture_path", ["../outside.txt", "nested/../fixture.txt", "/tmp/outside.txt"]
)
def test_manifest_rejects_fixture_paths_outside_skill(tmp_path: Path, fixture_path: str) -> None:
    payload = {
        "manifest_version": 1,
        "skill_name": "test",
        "recommended_suites": {"gating": [1], "regression": [1]},
        "evals": [
            {
                "id": 1,
                "prompt": "test",
                "expected_output": "test",
                "files": [fixture_path],
                "expectations": [],
                "grading_rules": [],
            }
        ],
    }

    with pytest.raises(ValueError, match="must stay within the skill directory"):
        validate_manifest(payload, tmp_path)


def test_all_checked_in_critical_graders_pass_their_controls() -> None:
    manifest = load_manifest(Path("slcli/skills/slcli/evals/evals.json"))

    for eval_entry in manifest["evals"]:
        for rule in eval_entry["grading_rules"]:
            if not rule["critical"]:
                continue
            reference_date = (
                date.fromisoformat(rule["control_reference_date"])
                if "control_reference_date" in rule
                else None
            )
            positive_passed, _ = evaluate_rule(
                rule["positive_control"], rule, reference_date=reference_date
            )
            negative_passed, _ = evaluate_rule(
                rule["negative_control"], rule, reference_date=reference_date
            )
            assert (
                positive_passed
            ), f"positive control failed: eval {eval_entry['id']} {rule['text']}"
            assert (
                not negative_passed
            ), f"negative control passed: eval {eval_entry['id']} {rule['text']}"


def test_webapp_packaging_fixture_is_valid() -> None:
    config_path = Path("slcli/skills/slcli/evals/files/webapp-package/nipkg.config.json")
    metadata = json.loads(config_path.read_text(encoding="utf-8"))

    validated = _validate_plugin_manager_metadata(
        metadata, require_build_dir=True, base_dir=config_path.parent
    )

    assert validated["package"] == "fleet-dashboard-webapp"
    assert validated["buildDir"] == "webapp-content"
    assert validated["iconFile"] == "icon.svg"
    assert (config_path.parent / validated["buildDir"]).is_dir()


def checked_in_rule(eval_id: int, text: str) -> dict[str, object]:
    """Return one checked-in grading rule by eval and text."""
    manifest = load_manifest(Path("slcli/skills/slcli/evals/evals.json"))
    eval_entry = next(entry for entry in manifest["evals"] if entry["id"] == eval_id)
    return next(rule for rule in eval_entry["grading_rules"] if rule["text"] == text)


def test_eval_one_rejects_constraints_split_across_commands() -> None:
    rule = checked_in_rule(1, "Combines product, status, and last-month filters in one invocation")
    response = (
        "slcli testmonitor result list --part-number BAT-MODEL-ABC-001 --status FAILED\n"
        "slcli testmonitor result list --filter 'startedAt >= @0 and startedAt < @1' "
        "--substitution 2026-08-01 --substitution 2026-09-01"
    )

    assert evaluate_rule(response, rule, reference_date=date(2026, 9, 8))[0] is False


def test_eval_one_full_query_accepts_current_previous_month_bounds() -> None:
    rule = checked_in_rule(1, "Combines product, status, and last-month filters in one invocation")
    response = (
        "slcli testmonitor result list --part-number BAT-MODEL-ABC-001 --status FAILED "
        "--filter 'startedAt >= @0 and startedAt < @1' "
        "--substitution 2026-09-01 --substitution 2026-10-01"
    )

    assert evaluate_rule(response, rule, reference_date=date(2026, 10, 8))[0] is True


def test_eval_four_accepts_operator_convenience_filter() -> None:
    rule = checked_in_rule(4, "Combines the full June failure query in one invocation")
    response = (
        "slcli testmonitor result list --part-number BATT-8 --operator xli --status FAILED "
        "--filter 'startedAt >= @0 and startedAt < @1' "
        "--substitution 2022-06-01 --substitution 2022-07-01"
    )

    assert evaluate_rule(response, rule)[0] is True


def test_dataframe_rule_requires_supported_case_sensitive_operation() -> None:
    rule = checked_in_rule(5, "Queries ProductionMetrics with the requested operator constraint")

    assert (
        evaluate_rule(
            "slcli dataframe query ProductionMetrics --where 'operator,EQUALS,J. Santos'", rule
        )[0]
        is True
    )
    assert (
        evaluate_rule(
            "slcli dataframe query ProductionMetrics --where 'operator,eq,J. Santos'", rule
        )[0]
        is False
    )


def test_dataframe_safety_guidance_can_quote_unsupported_sql() -> None:
    response = (
        "Do not use `SELECT * FROM ProductionMetrics WHERE operator = 'J. Santos'`. "
        "Use the supported dataframe command instead:\n\n"
        "slcli dataframe query ProductionMetrics "
        "--where 'operator,EQUALS,J. Santos' --format json"
    )
    manifest = load_manifest(Path("slcli/skills/slcli/evals/evals.json"))
    eval_entry = next(entry for entry in manifest["evals"] if entry["id"] == 5)
    critical_rules = [rule for rule in eval_entry["grading_rules"] if rule.get("critical")]

    assert all(evaluate_rule(response, rule)[0] for rule in critical_rules)


def test_workitem_template_create_rule_requires_valid_arguments() -> None:
    rule = checked_in_rule(7, "Uses the workitem template create command")

    assert evaluate_rule("slcli workitem template create", rule)[0] is False
    assert evaluate_rule("slcli workitem template create --file battery.json", rule)[0] is True
    assert (
        evaluate_rule(
            "slcli workitem template create --name cycle --type TestPlan "
            "--template-group battery",
            rule,
        )[0]
        is True
    )


def test_spec_rules_require_json_import_and_valid_verification_arguments() -> None:
    import_rule = checked_in_rule(9, "Uses the spec import command")
    verify_rule = checked_in_rule(9, "Includes a follow-up verification command")

    assert evaluate_rule("slcli spec import --file datasheet.csv", import_rule)[0] is False
    assert evaluate_rule("slcli spec import --file specifications.json", import_rule)[0] is True
    for invalid in ("slcli spec get", "slcli spec list", "slcli spec export"):
        assert evaluate_rule(invalid, verify_rule)[0] is False
    assert evaluate_rule("slcli spec get --id imported-spec-id", verify_rule)[0] is True
    assert evaluate_rule("slcli spec list --product BAT-MODEL-ABC-001", verify_rule)[0] is True


def test_webapp_packaging_rule_is_name_agnostic_and_option_order_independent() -> None:
    rule = checked_in_rule(8, "Includes the packaging workflow")
    response = (
        "slcli webapp manifest init another-app --license MIT --icon-file icon.svg "
        "--description 'A dashboard' --maintainer 'Team <team@example.com>' "
        "--section Dashboard\n"
        "slcli webapp pack --output app.nipkg --config another-app/nipkg.config.json"
    )

    assert evaluate_rule(response, rule)[0] is True

    @pytest.mark.parametrize(
        "config_path",
        [
            "/Users/QA Workspace/evals/files/webapp-package/nipkg.config.json",
            r"C:\QA Workspace\evals\files\webapp-package\nipkg.config.json",
        ],
    )
    def test_webapp_packaging_rule_accepts_spaced_unix_and_windows_paths(config_path: str) -> None:
        rule = checked_in_rule(11, "Uses the attached nipkg config for packaging")

        assert evaluate_rule(f'slcli webapp pack --config "{config_path}"', rule)[0] is True

    def test_webapp_packaging_rule_rejects_unrelated_config_path() -> None:
        rule = checked_in_rule(11, "Uses the attached nipkg config for packaging")

        assert (
            evaluate_rule(
                'slcli webapp pack --config "/Users/QA Workspace/evals/files/other-app/nipkg.config.json"',
                rule,
            )[0]
            is False
        )


def test_webapp_scaffold_rule_rejects_legacy_init_command() -> None:
    rule = checked_in_rule(8, "Uses a supported webapp scaffold command")

    assert evaluate_rule("slcli webapp new dashboard", rule)[0] is True
    assert evaluate_rule("slcli webapp init dashboard", rule)[0] is False
