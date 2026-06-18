#!/usr/bin/env python3
"""Bootstrap weighted choice shares and segment lift from JSONL choice results."""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


PROBABILITY_KEYS = (
    "choice_probability",
    "choice_probabilities",
    "probabilities",
    "final_probabilities",
)
CHOICE_KEYS = ("choice", "final_choice", "selected_option")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: expected a JSON object")
            value["_line_number"] = line_number
            records.append(value)
    return records


def get_nested(record: dict[str, Any], dotted_path: str) -> Any:
    value: Any = record
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def get_weight(record: dict[str, Any]) -> float:
    for key in ("population_weight", "weight", "sample_weight"):
        value = record.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 1.0


def get_choice_distribution(record: dict[str, Any]) -> dict[str, float]:
    for key in CHOICE_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value:
            return {value: 1.0}
    for key in PROBABILITY_KEYS:
        value = record.get(key)
        if isinstance(value, dict):
            return {
                str(alt): float(prob)
                for alt, prob in value.items()
                if isinstance(prob, (int, float))
            }
    raise ValueError(
        f"line {record.get('_line_number')}: missing discrete choice "
        f"({', '.join(CHOICE_KEYS)}) or probability object "
        f"({', '.join(PROBABILITY_KEYS)})"
    )


def weighted_shares(records: list[dict[str, Any]]) -> dict[str, float]:
    numerators: dict[str, float] = defaultdict(float)
    denominator = 0.0
    for record in records:
        weight = get_weight(record)
        denominator += weight
        for alternative, probability in get_choice_distribution(record).items():
            numerators[alternative] += weight * probability
    if denominator <= 0:
        raise ValueError("total weight must be positive")
    return {alternative: value / denominator for alternative, value in numerators.items()}


def total_weight(records: list[dict[str, Any]]) -> float:
    return sum(get_weight(record) for record in records)


def effective_sample_size(records: list[dict[str, Any]]) -> float:
    weights = [get_weight(record) for record in records]
    denominator = sum(weight * weight for weight in weights)
    if denominator <= 0:
        return 0.0
    return (sum(weights) ** 2) / denominator


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def summarize_draws(draws: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    alternatives = sorted({alternative for draw in draws for alternative in draw})
    summary: dict[str, dict[str, float]] = {}
    for alternative in alternatives:
        values = [draw.get(alternative, 0.0) for draw in draws]
        summary[alternative] = {
            "mean": sum(values) / len(values),
            "p2_5": percentile(values, 0.025),
            "p50": percentile(values, 0.5),
            "p97_5": percentile(values, 0.975),
        }
    return summary


def bootstrap_records(
    records: list[dict[str, Any]], iterations: int, rng: random.Random
) -> list[dict[str, float]]:
    draws: list[dict[str, float]] = []
    n = len(records)
    for _ in range(iterations):
        sample = [records[rng.randrange(n)] for _ in range(n)]
        draws.append(weighted_shares(sample))
    return draws


def labels_for_field(record: dict[str, Any], field: str) -> list[str]:
    value = get_nested(record, field)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def segment_records(
    records: list[dict[str, Any]], segment_fields: list[str]
) -> dict[str, list[dict[str, Any]]]:
    segments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for field in segment_fields:
            for label in labels_for_field(record, field):
                segments[f"{field}:{label}"].append(record)
    return segments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("choice_results", type=Path)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--segment-field", action="append", default=[])
    parser.add_argument("--min-count", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    records = load_jsonl(args.choice_results)
    if not records:
        raise ValueError("choice results file is empty")

    rng = random.Random(args.seed)
    point = weighted_shares(records)
    all_weight = total_weight(records)
    overall_draws = bootstrap_records(records, args.iterations, rng)
    result: dict[str, Any] = {
        "record_count": len(records),
        "effective_sample_size": effective_sample_size(records),
        "total_weight": all_weight,
        "iterations": args.iterations,
        "seed": args.seed,
        "overall": {
            "point": point,
            "intervals": summarize_draws(overall_draws),
        },
        "segments": [],
    }

    overall_point = point
    for segment_id, subset in sorted(segment_records(records, args.segment_field).items()):
        if len(subset) < args.min_count:
            continue
        segment_point = weighted_shares(subset)
        segment_weight = total_weight(subset)
        segment_draws = bootstrap_records(subset, args.iterations, rng)
        lifts = {
            alternative: segment_point.get(alternative, 0.0)
            - overall_point.get(alternative, 0.0)
            for alternative in sorted(set(segment_point) | set(overall_point))
        }
        result["segments"].append(
            {
                "segment_id": segment_id,
                "sample_count": len(subset),
                "effective_sample_size": effective_sample_size(subset),
                "weighted_population_share": segment_weight / all_weight
                if all_weight
                else 0.0,
                "point": segment_point,
                "lift_vs_overall": lifts,
                "intervals": summarize_draws(segment_draws),
            }
        )

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
