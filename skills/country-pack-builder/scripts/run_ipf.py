#!/usr/bin/env python3
"""Run iterative proportional fitting over seed statistical cells.

Inputs:
- seed cells JSONL from `country_pack_to_cells.py`
- margins JSON with one or more target margin definitions

Margin format:
{
  "separator": "|",
  "margins": [
    {"name": "sex", "variables": ["sex"], "targets": {"female": 3415025, "male": 3231978}},
    {"name": "region", "variables": ["region"], "targets": {"Belgrade": 1681405}}
  ]
}

For multi-variable margins, join values with the separator, for example:
"Belgrade|female".
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: expected JSON object")
            value["_line_number"] = line_number
            records.append(value)
    if not records:
        raise ValueError("seed cells file is empty")
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            clean = {key: value for key, value in record.items() if key != "_line_number"}
            handle.write(json.dumps(clean, ensure_ascii=False, sort_keys=True) + "\n")


def get_var(record: dict[str, Any], variable: str) -> str:
    hard = record.get("hard")
    if isinstance(hard, dict) and variable in hard:
        return str(hard[variable])
    if variable in record:
        return str(record[variable])
    raise KeyError(f"line {record.get('_line_number')}: missing variable {variable!r}")


def margin_key(record: dict[str, Any], variables: list[str], separator: str) -> str:
    return separator.join(get_var(record, variable) for variable in variables)


def get_weight(record: dict[str, Any]) -> float:
    for key in ("population_weight", "ipf_weight", "seed_weight", "weight"):
        value = record.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 1.0


def set_weight(record: dict[str, Any], value: float) -> None:
    record["ipf_weight"] = value
    record["population_weight"] = value
    record["ipf_ready"] = True


def parse_margins(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    separator = str(raw.get("separator", "|"))
    margins = raw.get("margins")
    if not isinstance(margins, list) or not margins:
        raise ValueError("margins JSON must contain a non-empty 'margins' array")
    parsed: list[dict[str, Any]] = []
    for index, margin in enumerate(margins):
        if not isinstance(margin, dict):
            raise ValueError(f"margin {index}: expected object")
        variables = margin.get("variables")
        targets = margin.get("targets")
        if not isinstance(variables, list) or not variables or not all(isinstance(v, str) for v in variables):
            raise ValueError(f"margin {index}: variables must be a non-empty string array")
        if not isinstance(targets, dict) or not targets:
            raise ValueError(f"margin {index}: targets must be a non-empty object")
        parsed_targets: dict[str, float] = {}
        for key, value in targets.items():
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"margin {index}: target {key!r} must be a non-negative number")
            parsed_targets[str(key)] = float(value)
        parsed.append({"name": str(margin.get("name", f"margin_{index}")), "variables": variables, "targets": parsed_targets})
    return parsed, separator


def current_totals(records: list[dict[str, Any]], variables: list[str], separator: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for record in records:
        totals[margin_key(record, variables, separator)] += get_weight(record)
    return dict(totals)


def apply_margin(records: list[dict[str, Any]], margin: dict[str, Any], separator: str) -> list[dict[str, Any]]:
    variables = margin["variables"]
    targets = margin["targets"]
    totals = current_totals(records, variables, separator)
    issues: list[dict[str, Any]] = []
    ratios: dict[str, float] = {}

    for key, target in targets.items():
        current = totals.get(key, 0.0)
        if current <= 0 and target > 0:
            issues.append({"key": key, "issue": "positive_target_zero_current", "target": target})
            continue
        if current > 0:
            ratios[key] = target / current

    for record in records:
        key = margin_key(record, variables, separator)
        if key in ratios:
            set_weight(record, get_weight(record) * ratios[key])
    return issues


def margin_errors(records: list[dict[str, Any]], margins: list[dict[str, Any]], separator: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for margin in margins:
        totals = current_totals(records, margin["variables"], separator)
        max_abs = 0.0
        max_rel = 0.0
        details: dict[str, dict[str, float]] = {}
        for key, target in margin["targets"].items():
            current = totals.get(key, 0.0)
            abs_error = current - target
            rel_error = abs(abs_error) / target if target else abs(abs_error)
            max_abs = max(max_abs, abs(abs_error))
            max_rel = max(max_rel, rel_error)
            details[key] = {"target": target, "current": current, "abs_error": abs_error, "rel_error": rel_error}
        errors.append(
            {
                "name": margin["name"],
                "variables": margin["variables"],
                "max_abs_error": max_abs,
                "max_rel_error": max_rel,
                "details": details,
            }
        )
    return errors


def total_weight(records: list[dict[str, Any]]) -> float:
    return sum(get_weight(record) for record in records)


def run_ipf(records: list[dict[str, Any]], margins: list[dict[str, Any]], separator: str, iterations: int, tolerance: float) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    converged = False
    final_errors: list[dict[str, Any]] = []
    completed_iterations = 0

    for iteration in range(1, iterations + 1):
        completed_iterations = iteration
        for margin in margins:
            warnings.extend({"margin": margin["name"], **issue} for issue in apply_margin(records, margin, separator))
        final_errors = margin_errors(records, margins, separator)
        max_rel_error = max((item["max_rel_error"] for item in final_errors), default=0.0)
        if max_rel_error <= tolerance:
            converged = True
            break

    for record in records:
        trace = record.get("calibration_trace")
        if not isinstance(trace, dict):
            trace = {}
        trace["ipf"] = {
            "method": "iterative_proportional_fitting",
            "iterations": completed_iterations,
            "converged": converged,
            "tolerance": tolerance,
        }
        record["calibration_trace"] = trace

    return {
        "record_count": len(records),
        "iterations_requested": iterations,
        "iterations_completed": completed_iterations,
        "converged": converged,
        "tolerance": tolerance,
        "total_weight": total_weight(records),
        "margin_errors": final_errors,
        "warning_count": len(warnings),
        "warnings": warnings[:100],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed_cells", type=Path)
    parser.add_argument("margins", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iterations <= 0:
        raise ValueError("--iterations must be positive")
    if args.tolerance < 0:
        raise ValueError("--tolerance must be non-negative")
    records = load_jsonl(args.seed_cells)
    margins, separator = parse_margins(load_json(args.margins))
    audit = run_ipf(records, margins, separator, args.iterations, args.tolerance)
    write_jsonl(args.output, records)
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if audit["converged"] and audit["warning_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
