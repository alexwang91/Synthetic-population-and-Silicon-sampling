#!/usr/bin/env python3
"""Validate LLM choice quality risks beyond row-schema correctness.

This validator is designed for synthetic respondent outputs. It does not decide
whether the market result is true. It checks known risk patterns from recent LLM
survey methodology work:

- variance compression: choices, reasons, or confidence collapse into too few values
- weak subgroup differentiation: important subgroups show no meaningful variation
- prompt/order sensitivity: choices appear overly tied to presented position or prompt variant
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VALIDATOR_VERSION = "0.1.0"
DEFAULT_SUBGROUP_FIELDS = ["region", "sex", "education_level", "income_decile", "settlement_type", "employment_status"]
CHOICES = ["focal_product", "competitor", "none_or_delay"]


class IssueSink:
    def __init__(self) -> None:
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    def error(self, issue: str, **extra: Any) -> None:
        payload = {"issue": issue}
        payload.update(extra)
        self.errors.append(payload)

    def warning(self, issue: str, **extra: Any) -> None:
        payload = {"issue": issue}
        payload.update(extra)
        self.warnings.append(payload)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            value["_line_number"] = line_number
            yield value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def numeric(value: Any, default: float = 0.0) -> float:
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


def weighted_counts(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    counts: dict[str, float] = defaultdict(float)
    for row in rows:
        value = str(row.get(key) or "missing")
        weight = numeric(row.get("population_weight"), 1.0)
        if weight <= 0:
            weight = 1.0
        counts[value] += weight
    return dict(counts)


def shares(counts: dict[str, float]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {key: 0.0 for key in counts}
    return {key: value / total for key, value in counts.items()}


def entropy_from_shares(share_map: dict[str, float]) -> float:
    return -sum(value * math.log(value, 2) for value in share_map.values() if value > 0)


def normalized_entropy(share_map: dict[str, float]) -> float:
    positive = [value for value in share_map.values() if value > 0]
    if len(positive) <= 1:
        return 0.0
    return entropy_from_shares(share_map) / math.log(len(positive), 2)


def load_personas(personas_path: Path) -> dict[str, dict[str, Any]]:
    personas = {}
    for row in iter_jsonl(personas_path):
        persona_id = str(row.get("persona_id") or "")
        if persona_id:
            personas[persona_id] = row
    return personas


def choice_position(row: dict[str, Any]) -> str | None:
    controls = row.get("generation_controls")
    if not isinstance(controls, dict):
        return None
    order = controls.get("presented_alternative_order")
    chosen_id = row.get("chosen_alternative_id")
    if not isinstance(order, list) or chosen_id is None:
        return None
    order_str = [str(item) for item in order]
    try:
        return str(order_str.index(str(chosen_id)) + 1)
    except ValueError:
        return None


def subgroup_choice_analysis(
    rows: list[dict[str, Any]],
    personas: dict[str, dict[str, Any]],
    fields: list[str],
    min_group_weight: float,
    min_meaningful_delta: float,
    sink: IssueSink,
) -> dict[str, Any]:
    overall = shares(weighted_counts(rows, "choice"))
    analysis: dict[str, Any] = {}
    for field in fields:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            persona = personas.get(str(row.get("persona_id") or ""), {})
            hard = persona.get("hard", {}) if isinstance(persona.get("hard"), dict) else {}
            group = str(hard.get(field, "missing"))
            groups[group].append(row)
        group_rows = []
        max_abs_delta = 0.0
        valid_group_count = 0
        for group, group_data in sorted(groups.items()):
            group_weight = sum(max(numeric(row.get("population_weight"), 1.0), 0.0) for row in group_data)
            if group_weight < min_group_weight:
                continue
            valid_group_count += 1
            group_shares = shares(weighted_counts(group_data, "choice"))
            deltas = {choice: group_shares.get(choice, 0.0) - overall.get(choice, 0.0) for choice in set(CHOICES) | set(overall) | set(group_shares)}
            local_max = max((abs(value) for value in deltas.values()), default=0.0)
            max_abs_delta = max(max_abs_delta, local_max)
            group_rows.append(
                {
                    "group": group,
                    "weight": group_weight,
                    "record_count": len(group_data),
                    "shares": group_shares,
                    "max_abs_delta_from_overall": local_max,
                }
            )
        analysis[field] = {
            "valid_group_count": valid_group_count,
            "max_abs_delta_from_overall": max_abs_delta,
            "groups": group_rows,
        }
        if valid_group_count >= 2 and max_abs_delta < min_meaningful_delta:
            sink.warning(
                "low_subgroup_differentiation",
                field=field,
                valid_group_count=valid_group_count,
                max_abs_delta_from_overall=max_abs_delta,
                min_meaningful_delta=min_meaningful_delta,
            )
    return analysis


def validate_quality(
    personas_path: Path,
    choice_results_path: Path,
    subgroup_fields: list[str],
    min_group_weight: float,
    min_choice_entropy: float,
    max_choice_share: float,
    min_meaningful_delta: float,
    max_position_share: float,
) -> dict[str, Any]:
    sink = IssueSink()
    personas = load_personas(personas_path)
    rows = list(iter_jsonl(choice_results_path))
    if not rows:
        sink.error("no_choice_rows")
        return summary(rows, personas, {}, {}, {}, sink, subgroup_fields)

    missing_personas = [row.get("persona_id") for row in rows if str(row.get("persona_id") or "") not in personas]
    if missing_personas:
        sink.warning("choice_rows_missing_persona_records", count=len(missing_personas), examples=missing_personas[:10])

    choice_counts = weighted_counts(rows, "choice")
    choice_shares = shares(choice_counts)
    choice_entropy = normalized_entropy(choice_shares)
    max_observed_choice_share = max(choice_shares.values(), default=0.0)
    if len([value for value in choice_counts.values() if value > 0]) <= 1:
        sink.error("choice_collapse_single_option", choice_shares=choice_shares)
    elif choice_entropy < min_choice_entropy:
        sink.warning("low_choice_distribution_entropy", normalized_entropy=choice_entropy, min_choice_entropy=min_choice_entropy, choice_shares=choice_shares)
    if max_observed_choice_share > max_choice_share:
        sink.warning("dominant_choice_share", max_choice_share=max_observed_choice_share, threshold=max_choice_share, choice_shares=choice_shares)

    confidence_counts = weighted_counts(rows, "answer_confidence")
    confidence_shares = shares(confidence_counts)
    driver_counter: Counter[str] = Counter()
    barrier_counter: Counter[str] = Counter()
    for row in rows:
        for driver in row.get("main_drivers", []) if isinstance(row.get("main_drivers"), list) else []:
            driver_counter[str(driver)] += 1
        for barrier in row.get("main_barriers", []) if isinstance(row.get("main_barriers"), list) else []:
            barrier_counter[str(barrier)] += 1
    if len(driver_counter) < 3 and len(rows) >= 20:
        sink.warning("low_driver_variety", distinct_driver_count=len(driver_counter))
    if len(barrier_counter) < 3 and len(rows) >= 20:
        sink.warning("low_barrier_variety", distinct_barrier_count=len(barrier_counter))

    position_values = []
    for row in rows:
        position = choice_position(row)
        if position:
            position_values.append({"position": position, "population_weight": row.get("population_weight", 1.0)})
    position_shares: dict[str, float] = {}
    if position_values:
        position_shares = shares(weighted_counts(position_values, "position"))
        max_pos_share = max(position_shares.values(), default=0.0)
        if max_pos_share > max_position_share:
            sink.warning("possible_position_or_order_bias", position_shares=position_shares, max_position_share=max_pos_share, threshold=max_position_share)

    variants = weighted_counts([{"prompt_variant": (row.get("generation_controls") or {}).get("prompt_variant"), "population_weight": row.get("population_weight", 1.0)} for row in rows], "prompt_variant")
    subgroup_analysis = subgroup_choice_analysis(rows, personas, subgroup_fields, min_group_weight, min_meaningful_delta, sink)
    return summary(
        rows,
        personas,
        {
            "weighted_counts": choice_counts,
            "weighted_shares": choice_shares,
            "normalized_entropy": choice_entropy,
            "max_observed_choice_share": max_observed_choice_share,
        },
        {
            "weighted_counts": confidence_counts,
            "weighted_shares": confidence_shares,
        },
        {
            "distinct_driver_count": len(driver_counter),
            "distinct_barrier_count": len(barrier_counter),
            "top_drivers": driver_counter.most_common(10),
            "top_barriers": barrier_counter.most_common(10),
            "position_shares": position_shares,
            "prompt_variant_counts": variants,
            "subgroup_choice_analysis": subgroup_analysis,
        },
        sink,
        subgroup_fields,
    )


def summary(
    rows: list[dict[str, Any]],
    personas: dict[str, dict[str, Any]],
    choice_distribution: dict[str, Any],
    confidence_distribution: dict[str, Any],
    diagnostics: dict[str, Any],
    sink: IssueSink,
    subgroup_fields: list[str],
) -> dict[str, Any]:
    return {
        "validator_version": VALIDATOR_VERSION,
        "record_count": len(rows),
        "persona_count": len(personas),
        "subgroup_fields": subgroup_fields,
        "choice_distribution": choice_distribution,
        "confidence_distribution": confidence_distribution,
        "diagnostics": diagnostics,
        "error_count": len(sink.errors),
        "warning_count": len(sink.warnings),
        "errors": sink.errors[:200],
        "warnings": sink.warnings[:200],
        "passes_llm_choice_quality_validation": len(sink.errors) == 0,
        "warning_policy": "Warnings flag likely LLM survey risks such as variance compression, weak subgroup differentiation, or order sensitivity; they do not automatically invalidate a run.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("personas_enriched", type=Path)
    parser.add_argument("choice_results", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--subgroup-fields", default=",".join(DEFAULT_SUBGROUP_FIELDS))
    parser.add_argument("--min-group-weight", type=float, default=1.0)
    parser.add_argument("--min-choice-entropy", type=float, default=0.25)
    parser.add_argument("--max-choice-share", type=float, default=0.92)
    parser.add_argument("--min-meaningful-delta", type=float, default=0.03)
    parser.add_argument("--max-position-share", type=float, default=0.70)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    subgroup_fields = [field.strip() for field in args.subgroup_fields.split(",") if field.strip()]
    result = validate_quality(
        args.personas_enriched,
        args.choice_results,
        subgroup_fields,
        args.min_group_weight,
        args.min_choice_entropy,
        args.max_choice_share,
        args.min_meaningful_delta,
        args.max_position_share,
    )
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
