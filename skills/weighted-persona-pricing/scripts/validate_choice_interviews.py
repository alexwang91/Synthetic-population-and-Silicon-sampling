#!/usr/bin/env python3
"""Validate identity-first choice interview JSONL records."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "persona_id",
    "population_weight",
    "choice",
    "interview_response",
    "main_drivers",
    "main_barriers",
    "switch_conditions",
    "answer_confidence",
}
PROBABILITY_FIELDS = {
    "choice_probability",
    "choice_probabilities",
    "probabilities",
    "final_probabilities",
}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
DEFAULT_ALLOWED_CHOICES = {"focal_product", "competitor", "none_or_delay"}
CONTAMINATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\baggregate share\b",
        r"\boverall share\b",
        r"\bmarket share\b",
        r"\bother respondents?\b",
        r"\bprevious respondents?\b",
        r"\bpanel result\b",
        r"\bquota\b",
        r"\btarget proportion\b",
    )
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
                raise ValueError(f"line {line_number}: expected object")
            value["_line_number"] = line_number
            rows.append(value)
    return rows


def is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def mentions_contamination(text: str) -> bool:
    return any(pattern.search(text) for pattern in CONTAMINATION_PATTERNS)


def validate_record(
    row: dict[str, Any],
    allowed_choices: set[str],
    require_controls: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    line = row.get("_line_number")
    persona_id = row.get("persona_id")

    missing = sorted(field for field in REQUIRED_FIELDS if field not in row)
    if missing:
        errors.append(
            {
                "line": line,
                "persona_id": persona_id,
                "issue": "missing_required",
                "fields": missing,
            }
        )

    if any(field in row for field in PROBABILITY_FIELDS):
        issue = "probability_field_present"
        target = errors if "choice" not in row else warnings
        target.append({"line": line, "persona_id": persona_id, "issue": issue})

    weight = row.get("population_weight")
    if not isinstance(weight, (int, float)) or weight <= 0:
        errors.append(
            {"line": line, "persona_id": persona_id, "issue": "invalid_weight"}
        )

    choice = row.get("choice")
    if "choice" in row and choice not in allowed_choices:
        errors.append(
            {
                "line": line,
                "persona_id": persona_id,
                "issue": "invalid_choice",
                "choice": choice,
            }
        )

    response = row.get("interview_response")
    if "interview_response" in row and (
        not isinstance(response, str) or len(response.strip()) < 20
    ):
        errors.append(
            {
                "line": line,
                "persona_id": persona_id,
                "issue": "interview_response_too_short",
            }
        )
    if isinstance(response, str) and mentions_contamination(response):
        errors.append(
            {
                "line": line,
                "persona_id": persona_id,
                "issue": "contamination_text_detected",
            }
        )

    for field in ("main_drivers", "main_barriers", "switch_conditions"):
        if field in row and not is_string_list(row.get(field)):
            errors.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": f"invalid_{field}",
                }
            )

    confidence = row.get("answer_confidence")
    if "answer_confidence" in row and confidence not in ALLOWED_CONFIDENCE:
        errors.append(
            {
                "line": line,
                "persona_id": persona_id,
                "issue": "invalid_answer_confidence",
                "answer_confidence": confidence,
            }
        )

    isolation = row.get("isolation")
    generation_controls = row.get("generation_controls")
    quality_controls = row.get("quality_controls")
    if require_controls:
        for field, value in (
            ("isolation", isolation),
            ("generation_controls", generation_controls),
            ("quality_controls", quality_controls),
        ):
            if not isinstance(value, dict):
                errors.append(
                    {
                        "line": line,
                        "persona_id": persona_id,
                        "issue": f"missing_{field}",
                    }
                )

    if isinstance(isolation, dict):
        if isolation.get("context_scope") not in {None, "individual", "single_persona"}:
            errors.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "contamination_context_scope",
                    "context_scope": isolation.get("context_scope"),
                }
            )
        if isolation.get("saw_other_answers") is True:
            errors.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "contamination_saw_other_answers",
                }
            )
        if isolation.get("saw_aggregate_results") is True:
            errors.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "contamination_saw_aggregate_results",
                }
            )

    if isinstance(generation_controls, dict):
        temperature = generation_controls.get("temperature")
        if temperature is not None and (
            not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 1
        ):
            errors.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "invalid_temperature",
                    "temperature": temperature,
                }
            )
        if "seed" not in generation_controls:
            warnings.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "missing_seed",
                }
            )
        if "prompt_variant" not in generation_controls:
            warnings.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "missing_prompt_variant",
                }
            )

    if isinstance(quality_controls, dict):
        judge = quality_controls.get("consistency_judge")
        if judge not in {None, "pass", "review", "fail"}:
            errors.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "invalid_consistency_judge",
                    "consistency_judge": judge,
                }
            )
        if judge == "fail":
            errors.append(
                {
                    "line": line,
                    "persona_id": persona_id,
                    "issue": "consistency_judge_failed",
                }
            )

    return errors, warnings


def validate(
    rows: list[dict[str, Any]],
    allowed_choices: set[str],
    require_controls: bool,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    confidence_counts: Counter[str] = Counter()
    choice_counts: Counter[str] = Counter()
    control_counts: Counter[str] = Counter()

    for row in rows:
        row_errors, row_warnings = validate_record(row, allowed_choices, require_controls)
        errors.extend(row_errors)
        warnings.extend(row_warnings)
        if isinstance(row.get("answer_confidence"), str):
            confidence_counts[row["answer_confidence"]] += 1
        if isinstance(row.get("choice"), str):
            choice_counts[row["choice"]] += 1
        for field in ("isolation", "generation_controls", "quality_controls"):
            if isinstance(row.get(field), dict):
                control_counts[field] += 1

    total = len(rows)
    return {
        "record_count": total,
        "choice_counts": dict(choice_counts),
        "answer_confidence_counts": dict(confidence_counts),
        "control_presence": dict(control_counts),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors[:50],
        "warnings": warnings[:50],
        "choice_record_contract_pass_rate": (
            (total - len({error.get("line") for error in errors})) / total if total else 0
        ),
        "passes_choice_interview_integrity": len(errors) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("choice_results", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--allowed-choice", action="append", default=[])
    parser.add_argument("--require-controls", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    rows = load_jsonl(args.choice_results)
    allowed_choices = set(args.allowed_choice) or DEFAULT_ALLOWED_CHOICES
    summary = validate(rows, allowed_choices, args.require_controls)
    if args.strict and summary["warning_count"]:
        summary["passes_choice_interview_integrity"] = False

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.audit:
        args.audit.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if summary["passes_choice_interview_integrity"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
