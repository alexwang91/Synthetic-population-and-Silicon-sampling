#!/usr/bin/env python3
"""Validate batch audit coverage thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def validate_gate(audit: dict[str, Any], max_failure_rate: float, min_coverage_rate: float) -> dict[str, Any]:
    prompt_count = int(as_float(audit.get("prompt_count"), 0.0))
    response_count = int(as_float(audit.get("response_count"), 0.0))
    failure_count = int(as_float(audit.get("failure_count"), 0.0))
    issues: list[dict[str, Any]] = []

    if prompt_count <= 0:
        failure_rate = 1.0
        coverage_rate = 0.0
        issues.append({"issue": "prompt_count_must_be_positive"})
    else:
        failure_rate = failure_count / prompt_count
        coverage_rate = as_float(audit.get("coverage_rate"), response_count / prompt_count)

    if failure_rate > max_failure_rate:
        issues.append({"issue": "failure_rate_exceeds_threshold", "failure_rate": failure_rate, "max_failure_rate": max_failure_rate})
    if coverage_rate < min_coverage_rate:
        issues.append({"issue": "coverage_rate_below_threshold", "coverage_rate": coverage_rate, "min_coverage_rate": min_coverage_rate})

    return {
        "mode": "validate_llm_batch_audit",
        "prompt_count": prompt_count,
        "response_count": response_count,
        "failure_count": failure_count,
        "failure_rate": failure_rate,
        "coverage_rate": coverage_rate,
        "max_failure_rate": max_failure_rate,
        "min_coverage_rate": min_coverage_rate,
        "issue_count": len(issues),
        "issues": issues,
        "passes_llm_batch_gate": len(issues) == 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--max-failure-rate", type=float, default=0.005)
    parser.add_argument("--min-coverage-rate", type=float, default=0.995)
    parser.add_argument("--audit-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.max_failure_rate <= 1:
        raise ValueError("--max-failure-rate must be in [0,1]")
    if not 0 <= args.min_coverage_rate <= 1:
        raise ValueError("--min-coverage-rate must be in [0,1]")
    result = validate_gate(load_json(args.audit), args.max_failure_rate, args.min_coverage_rate)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.audit_output:
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        args.audit_output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["passes_llm_batch_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
