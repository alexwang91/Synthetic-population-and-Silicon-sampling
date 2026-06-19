#!/usr/bin/env python3
"""Validate persona-level coherence before choice simulation.

This validator is a quality-control layer for enriched synthetic respondents.
It checks structural integrity, bounded scores, audit traces, and selected
cross-field contradictions. It does not judge whether inferred traits are true
consumer facts.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = {"persona_id", "population_weight", "hard", "soft"}
REQUIRED_SOFT_SECTIONS = {"media_habits", "shopping_habits", "psychographics", "category_priors", "soft_trait_trace"}
BOUNDED_SCORE_SECTIONS = {"media_habits", "shopping_habits", "psychographics", "category_priors"}
UNBOUNDED_CATEGORY_PRIOR_FIELDS = {"comfortable_price_multiplier", "stretch_price_multiplier"}
OPTIONAL_HARD_FIELDS = {"region", "sex", "age_band", "education_level", "income_decile", "household_size", "settlement_type", "employment_status"}


class IssueSink:
    def __init__(self) -> None:
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    def error(self, record: dict[str, Any], issue: str, **extra: Any) -> None:
        self.errors.append(self._issue(record, issue, extra))

    def warning(self, record: dict[str, Any], issue: str, **extra: Any) -> None:
        self.warnings.append(self._issue(record, issue, extra))

    @staticmethod
    def _issue(record: dict[str, Any], issue: str, extra: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "line": record.get("_line_number"),
            "persona_id": record.get("persona_id"),
            "issue": issue,
        }
        payload.update(extra)
        return payload


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
        raise ValueError("persona file is empty")
    return records


def numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def get_soft(record: dict[str, Any]) -> dict[str, Any] | None:
    value = record.get("soft")
    return value if isinstance(value, dict) else None


def get_hard(record: dict[str, Any]) -> dict[str, Any] | None:
    value = record.get("hard")
    return value if isinstance(value, dict) else None


def score(soft: dict[str, Any], section: str, field: str) -> float | None:
    section_value = soft.get(section)
    if not isinstance(section_value, dict):
        return None
    return numeric(section_value.get(field))


def hard_income_decile(hard: dict[str, Any]) -> float | None:
    return numeric(hard.get("income_decile") or hard.get("household_income_decile"))


def hard_household_size(hard: dict[str, Any]) -> float | None:
    return numeric(hard.get("household_size"))


def validate_structure(record: dict[str, Any], sink: IssueSink) -> None:
    missing = sorted(REQUIRED_TOP_LEVEL - set(record))
    if missing:
        sink.error(record, "missing_top_level_fields", fields=missing)

    weight = numeric(record.get("population_weight"))
    if weight is None or weight <= 0:
        sink.error(record, "invalid_population_weight", value=record.get("population_weight"))

    hard = get_hard(record)
    if hard is None:
        sink.error(record, "hard_not_object")
    else:
        missing_hard = sorted(field for field in OPTIONAL_HARD_FIELDS if field not in hard)
        if missing_hard:
            sink.warning(record, "missing_common_hard_fields", fields=missing_hard)

    soft = get_soft(record)
    if soft is None:
        sink.error(record, "soft_not_object")
        return

    missing_sections = sorted(REQUIRED_SOFT_SECTIONS - set(soft))
    if missing_sections:
        sink.error(record, "missing_soft_sections", sections=missing_sections)

    trace = soft.get("soft_trait_trace")
    if not isinstance(trace, dict):
        sink.error(record, "soft_trait_trace_not_object")
    else:
        if trace.get("llm_generated") is not False:
            sink.warning(record, "soft_trait_trace_not_marked_deterministic", llm_generated=trace.get("llm_generated"))
        if not trace.get("method"):
            sink.warning(record, "soft_trait_trace_missing_method")

    calibration_trace = record.get("calibration_trace")
    if not isinstance(calibration_trace, dict):
        sink.warning(record, "calibration_trace_missing_or_not_object")
    elif "soft_trait_expansion" not in calibration_trace:
        sink.warning(record, "calibration_trace_missing_soft_trait_expansion")


def validate_bounded_scores(record: dict[str, Any], sink: IssueSink) -> None:
    soft = get_soft(record)
    if not soft:
        return
    for section_name in BOUNDED_SCORE_SECTIONS:
        section = soft.get(section_name)
        if not isinstance(section, dict):
            continue
        for field, value in section.items():
            if section_name == "category_priors" and field in UNBOUNDED_CATEGORY_PRIOR_FIELDS:
                continue
            if isinstance(value, bool) or value is None or isinstance(value, str):
                continue
            score_value = numeric(value)
            if score_value is None:
                continue
            if score_value < 0.0 or score_value > 1.0:
                sink.error(record, "score_out_of_bounds", section=section_name, field=field, value=score_value)


def validate_cross_field_rules(record: dict[str, Any], sink: IssueSink) -> None:
    hard = get_hard(record)
    soft = get_soft(record)
    if not hard or not soft:
        return

    inc = hard_income_decile(hard)
    hh_size = hard_household_size(hard)
    digital = score(soft, "media_habits", "digital_intensity")
    online = score(soft, "shopping_habits", "online_purchase_readiness")
    offline = score(soft, "shopping_habits", "offline_store_reliance")
    price = score(soft, "psychographics", "price_sensitivity")
    budget = score(soft, "psychographics", "budget_pressure")
    household_burden = score(soft, "psychographics", "household_burden")
    risk = score(soft, "psychographics", "risk_aversion")
    novelty = score(soft, "psychographics", "novelty_seeking")
    affordability = score(soft, "category_priors", "category_affordability")
    need = score(soft, "category_priors", "need_activation")
    comfortable = score(soft, "category_priors", "comfortable_price_multiplier")
    stretch = score(soft, "category_priors", "stretch_price_multiplier")

    if inc is not None and inc >= 8 and price is not None and price > 0.85:
        sink.warning(record, "high_income_extreme_price_sensitivity", income_decile=inc, price_sensitivity=price)
    if inc is not None and inc <= 3 and price is not None and price < 0.25:
        sink.warning(record, "low_income_low_price_sensitivity", income_decile=inc, price_sensitivity=price)
    if inc is not None and inc <= 3 and budget is not None and budget < 0.25:
        sink.warning(record, "low_income_low_budget_pressure", income_decile=inc, budget_pressure=budget)
    if hh_size is not None and hh_size >= 5 and household_burden is not None and household_burden < 0.25:
        sink.warning(record, "large_household_low_household_burden", household_size=hh_size, household_burden=household_burden)

    if digital is not None and online is not None and digital < 0.25 and online > 0.75:
        sink.warning(record, "low_digital_high_online_purchase_readiness", digital_intensity=digital, online_purchase_readiness=online)
    if digital is not None and offline is not None and digital > 0.85 and offline > 0.85:
        sink.warning(record, "high_digital_high_offline_reliance", digital_intensity=digital, offline_store_reliance=offline)
    if risk is not None and novelty is not None and risk > 0.85 and novelty > 0.85:
        sink.warning(record, "high_risk_aversion_high_novelty_seeking", risk_aversion=risk, novelty_seeking=novelty)
    if affordability is not None and need is not None and affordability < 0.2 and need > 0.8:
        sink.warning(record, "low_affordability_high_need_activation", category_affordability=affordability, need_activation=need)

    if comfortable is not None and stretch is not None and comfortable > stretch:
        sink.error(record, "comfortable_multiplier_exceeds_stretch_multiplier", comfortable=comfortable, stretch=stretch)
    if comfortable is not None and (comfortable < 0.25 or comfortable > 1.6):
        sink.warning(record, "comfortable_price_multiplier_unusual", comfortable=comfortable)
    if stretch is not None and (stretch < 0.35 or stretch > 1.8):
        sink.warning(record, "stretch_price_multiplier_unusual", stretch=stretch)


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    sink = IssueSink()
    persona_ids: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    score_sums: dict[str, float] = defaultdict(float)
    score_counts: Counter[str] = Counter()

    for record in records:
        pid = record.get("persona_id")
        if isinstance(pid, str) and pid:
            persona_ids[pid] += 1
        else:
            sink.error(record, "invalid_persona_id", value=pid)
        stage_counts[str(record.get("persona_stage"))] += 1

        validate_structure(record, sink)
        validate_bounded_scores(record, sink)
        validate_cross_field_rules(record, sink)

        soft = get_soft(record) or {}
        cat = soft.get("category_priors") if isinstance(soft.get("category_priors"), dict) else {}
        if isinstance(cat, dict) and isinstance(cat.get("category"), str):
            category_counts[cat["category"]] += 1
        psych = soft.get("psychographics") if isinstance(soft.get("psychographics"), dict) else {}
        media = soft.get("media_habits") if isinstance(soft.get("media_habits"), dict) else {}
        for field in ("price_sensitivity", "risk_aversion", "budget_pressure", "review_dependency"):
            value = numeric(psych.get(field)) if isinstance(psych, dict) else None
            if value is not None:
                score_sums[field] += value
                score_counts[field] += 1
        value = numeric(media.get("digital_intensity")) if isinstance(media, dict) else None
        if value is not None:
            score_sums["digital_intensity"] += value
            score_counts["digital_intensity"] += 1

    for pid, count in persona_ids.items():
        if count > 1:
            sink.errors.append({"persona_id": pid, "issue": "duplicate_persona_id", "count": count})

    mean_scores = {
        field: round(score_sums[field] / score_counts[field], 4)
        for field in sorted(score_counts)
        if score_counts[field]
    }

    return {
        "record_count": len(records),
        "unique_persona_count": len(persona_ids),
        "stage_counts": dict(stage_counts),
        "category_counts": dict(category_counts),
        "mean_scores": mean_scores,
        "error_count": len(sink.errors),
        "warning_count": len(sink.warnings),
        "errors": sink.errors[:200],
        "warnings": sink.warnings[:200],
        "passes_persona_coherence": len(sink.errors) == 0,
        "warning_policy": "warnings indicate unusual inferred combinations; they do not necessarily invalidate the panel",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("personas_enriched", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_jsonl(args.personas_enriched)
    summary = validate_records(records)
    text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if summary["error_count"] > 0:
        return 1
    if args.fail_on_warning and summary["warning_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
