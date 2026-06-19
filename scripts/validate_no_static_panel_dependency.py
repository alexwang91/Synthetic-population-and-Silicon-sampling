#!/usr/bin/env python3
"""Check that scenario configs regenerate respondent panels from country inputs.

A valid scenario config should use country_pack, dimensions, margins, and
sample_size. It should not use a prior persona or choice file as the population
source.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VALIDATOR_VERSION = "0.1.0"
BLOCKED_INPUT_KEYS = {
    "personas",
    "persona_file",
    "personas_file",
    "personas_core",
    "personas_enriched",
    "input_personas",
    "panel_path",
    "choice_results",
    "choice_results_file",
    "input_choice_results",
}
REQUIRED_KEYS = {"country_pack", "dimensions", "sample_size", "product_scenario", "category", "category_price_index"}


class Issues:
    def __init__(self) -> None:
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    def error(self, issue: str, **extra: Any) -> None:
        item = {"issue": issue}
        item.update(extra)
        self.errors.append(item)

    def warning(self, issue: str, **extra: Any) -> None:
        item = {"issue": issue}
        item.update(extra)
        self.warnings.append(item)


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, "file_not_found"
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"
    if not isinstance(value, dict):
        return None, "json_root_not_object"
    return value, None


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_files(paths: list[Path]) -> list[Path]:
    output: list[Path] = []
    for path in paths:
        if path.is_dir():
            output.extend(sorted(item for item in path.rglob("*.json") if item.is_file()))
        else:
            output.append(path)
    return output


def is_scenario_config(value: dict[str, Any]) -> bool:
    return "country_pack" in value and "product_scenario" in value


def find_blocked_keys(value: dict[str, Any]) -> list[str]:
    return sorted(key for key in value.keys() if key in BLOCKED_INPUT_KEYS)


def validate_one(path: Path, value: dict[str, Any], issues: Issues) -> None:
    if not is_scenario_config(value):
        return
    missing = sorted(REQUIRED_KEYS - set(value.keys()))
    if missing:
        issues.error("missing_required_generation_keys", path=str(path), missing=missing)
    blocked = find_blocked_keys(value)
    if blocked:
        issues.error("blocked_prior_panel_inputs", path=str(path), keys=blocked)
    if "margins" not in value and "margins_inline" not in value:
        issues.error("missing_margins", path=str(path))
    if not isinstance(value.get("dimensions"), dict) or not value.get("dimensions"):
        issues.error("missing_dimensions", path=str(path))
    sample_size = value.get("sample_size")
    if not isinstance(sample_size, int) or sample_size <= 0:
        issues.error("invalid_sample_size", path=str(path), sample_size=sample_size)
    elif sample_size < 10_000:
        issues.warning("below_production_panel_size", path=str(path), sample_size=sample_size, production_default=10_000)
    policy = value.get("country_run_policy")
    if isinstance(policy, dict):
        if policy.get("regenerate_panel_from_country_pack") is not True:
            issues.error("policy_missing_regenerate_panel_flag", path=str(path))
        if policy.get("no_static_persona_panel_input") is not True:
            issues.error("policy_missing_no_prior_panel_flag", path=str(path))
    else:
        issues.warning("missing_country_run_policy", path=str(path))


def validate(paths: list[Path]) -> dict[str, Any]:
    issues = Issues()
    checked: list[str] = []
    scenario_count = 0
    for path in iter_files(paths):
        checked.append(str(path))
        value, error = load_json(path)
        if error:
            issues.warning("skipped_invalid_json", path=str(path), error=error)
            continue
        if value is None:
            continue
        if is_scenario_config(value):
            scenario_count += 1
        validate_one(path, value, issues)
    return {
        "validator_version": VALIDATOR_VERSION,
        "checked_file_count": len(checked),
        "scenario_config_count": scenario_count,
        "error_count": len(issues.errors),
        "warning_count": len(issues.warnings),
        "errors": issues.errors[:200],
        "warnings": issues.warnings[:200],
        "passes_country_run_dependency_validation": len(issues.errors) == 0,
        "checked_files": checked[:200],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("skills/weighted-persona-pricing/examples")])
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate(args.paths)
    if args.audit:
        write_json(args.audit, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["error_count"] > 0:
        return 1
    if args.fail_on_warning and result["warning_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
