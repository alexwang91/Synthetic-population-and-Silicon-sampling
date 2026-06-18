#!/usr/bin/env python3
"""Validate a weighted persona JSONL panel.

This is a lightweight integrity check. It does not replace census-fit,
coherence, or calibration analysis.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = {"persona_id", "population_weight", "hard"}
HTE_LABEL_FAMILIES = {
    "population",
    "capacity",
    "category_need",
    "decision_role",
    "price_value",
    "risk_trust",
    "brand_feature",
    "channel_media",
    "friction",
    "evidence",
}


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
                raise ValueError(f"line {line_number}: expected an object")
            value["_line_number"] = line_number
            records.append(value)
    return records


def validate(records: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [str(record.get("persona_id", "")) for record in records]
    id_counts = Counter(ids)
    duplicate_ids = sorted(
        persona_id for persona_id, count in id_counts.items() if persona_id and count > 1
    )

    missing_required: list[dict[str, Any]] = []
    non_positive_weights: list[dict[str, Any]] = []
    missing_hard_fields: Counter[str] = Counter()
    malformed_hte_labels: list[dict[str, Any]] = []
    hte_label_counts: Counter[str] = Counter()

    for record in records:
        missing = sorted(field for field in REQUIRED_TOP_LEVEL if field not in record)
        if missing:
            missing_required.append(
                {"line": record.get("_line_number"), "missing": missing}
            )

        weight = record.get("population_weight")
        if not isinstance(weight, (int, float)) or weight <= 0:
            non_positive_weights.append(
                {"line": record.get("_line_number"), "persona_id": record.get("persona_id")}
            )

        hard = record.get("hard")
        if isinstance(hard, dict):
            for field in ["age", "age_band", "sex", "region", "education_level"]:
                if field not in hard:
                    missing_hard_fields[field] += 1
        else:
            missing_hard_fields["hard_not_object"] += 1

        hte_labels = record.get("hte_labels")
        if hte_labels is not None:
            if not isinstance(hte_labels, dict):
                malformed_hte_labels.append(
                    {
                        "line": record.get("_line_number"),
                        "persona_id": record.get("persona_id"),
                        "issue": "hte_labels_not_object",
                    }
                )
            else:
                for family, labels in hte_labels.items():
                    if family not in HTE_LABEL_FAMILIES:
                        malformed_hte_labels.append(
                            {
                                "line": record.get("_line_number"),
                                "persona_id": record.get("persona_id"),
                                "issue": f"unknown_hte_family:{family}",
                            }
                        )
                    if not isinstance(labels, list) or not all(
                        isinstance(label, str) for label in labels
                    ):
                        malformed_hte_labels.append(
                            {
                                "line": record.get("_line_number"),
                                "persona_id": record.get("persona_id"),
                                "issue": f"hte_family_not_string_array:{family}",
                            }
                        )
                    else:
                        hte_label_counts[family] += len(labels)

    total_weight = sum(
        float(record.get("population_weight", 0))
        for record in records
        if isinstance(record.get("population_weight"), (int, float))
    )

    return {
        "record_count": len(records),
        "total_population_weight": total_weight,
        "duplicate_ids": duplicate_ids[:50],
        "duplicate_id_count": len(duplicate_ids),
        "missing_required_count": len(missing_required),
        "missing_required_examples": missing_required[:20],
        "non_positive_weight_count": len(non_positive_weights),
        "non_positive_weight_examples": non_positive_weights[:20],
        "missing_hard_fields": dict(missing_hard_fields),
        "malformed_hte_label_count": len(malformed_hte_labels),
        "malformed_hte_label_examples": malformed_hte_labels[:20],
        "hte_label_counts": dict(hte_label_counts),
        "passes_basic_integrity": not (
            duplicate_ids
            or missing_required
            or non_positive_weights
            or malformed_hte_labels
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl_path", type=Path)
    parser.add_argument(
        "--audit",
        type=Path,
        help="Optional path to write the validation summary as JSON.",
    )
    args = parser.parse_args()

    records = load_jsonl(args.jsonl_path)
    summary = validate(records)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)

    if args.audit:
        args.audit.write_text(text + "\n", encoding="utf-8")

    return 0 if summary["passes_basic_integrity"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
