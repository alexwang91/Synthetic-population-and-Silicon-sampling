#!/usr/bin/env python3
"""Expand hard persona skeletons with deterministic soft traits.

This script initializes respondent state for later pricing interviews. It uses
transparent conditional priors derived from hard fields such as age, education,
income, household size, settlement type, employment, and digital access.

It does not call an LLM and does not generate narrative stories or product
choices. All generated fields are marked as inferred soft traits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


SOFT_TRAIT_VERSION = "0.1.0"


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
        raise ValueError("input persona file is empty")
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            clean = {key: value for key, value in record.items() if key != "_line_number"}
            handle.write(json.dumps(clean, ensure_ascii=False, sort_keys=True) + "\n")


def norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def round_score(value: float) -> float:
    return round(clamp(value), 4)


def stable_noise(key: str, scale: float = 0.04) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    raw = int(digest[:12], 16) / float(16**12 - 1)
    return (raw - 0.5) * 2.0 * scale


def hard(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("hard")
    if not isinstance(value, dict):
        raise ValueError(f"line {record.get('_line_number')}: missing object field 'hard'")
    return value


def persona_key(record: dict[str, Any]) -> str:
    value = record.get("persona_id") or record.get("source_cell_id") or record.get("_line_number")
    return str(value)


def parse_numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def age_midpoint(attrs: dict[str, Any]) -> float | None:
    direct = parse_numeric(attrs.get("age"))
    if direct is not None:
        return direct
    raw = str(attrs.get("age_band") or attrs.get("age_group") or "").strip()
    if not raw:
        return None
    cleaned = raw.replace("–", "-").replace("to", "-").replace(" ", "")
    if "+" in cleaned:
        base = parse_numeric(cleaned.replace("+", ""))
        return base + 5 if base is not None else None
    if "-" in cleaned:
        left, right = cleaned.split("-", 1)
        lo = parse_numeric(left)
        hi = parse_numeric(right)
        if lo is not None and hi is not None:
            return (lo + hi) / 2.0
    return None


def income_score(attrs: dict[str, Any]) -> float:
    decile = parse_numeric(attrs.get("income_decile") or attrs.get("household_income_decile"))
    if decile is not None:
        return clamp((decile - 1.0) / 9.0)
    raw = norm(attrs.get("income_band") or attrs.get("income_level") or attrs.get("monthly_disposable_income_band"))
    mapping = {
        "very_low": 0.08,
        "low": 0.18,
        "lower": 0.22,
        "lower_middle": 0.35,
        "middle": 0.5,
        "medium": 0.5,
        "upper_middle": 0.68,
        "high": 0.82,
        "very_high": 0.94,
        "top": 0.96,
    }
    return mapping.get(raw, 0.5)


def education_score(attrs: dict[str, Any]) -> float:
    raw = norm(attrs.get("education_level") or attrs.get("education"))
    if not raw:
        return 0.5
    if any(token in raw for token in ("tertiary", "university", "higher", "bachelor", "master", "phd")):
        return 0.86
    if any(token in raw for token in ("secondary", "high_school", "vocational")):
        return 0.58
    if any(token in raw for token in ("primary", "elementary")):
        return 0.32
    if any(token in raw for token in ("none", "incomplete", "without")):
        return 0.14
    return 0.5


def urban_score(attrs: dict[str, Any]) -> float:
    raw = norm(attrs.get("urban_rural") or attrs.get("settlement_type") or attrs.get("municipality_type"))
    if any(token in raw for token in ("urban", "city", "metro", "capital")):
        return 0.86
    if any(token in raw for token in ("suburban", "commuter")):
        return 0.68
    if any(token in raw for token in ("town", "small_city")):
        return 0.55
    if any(token in raw for token in ("rural", "village", "other_settlement")):
        return 0.24
    return 0.5


def employment_pressure(attrs: dict[str, Any]) -> float:
    raw = norm(attrs.get("employment_status") or attrs.get("employment"))
    if any(token in raw for token in ("unemployed", "inactive", "not_in_labor_force")):
        return 0.86
    if "retired" in raw or "pension" in raw:
        return 0.72
    if "student" in raw:
        return 0.62
    if any(token in raw for token in ("part_time", "temporary", "informal")):
        return 0.58
    if any(token in raw for token in ("employed", "full_time", "self_employed")):
        return 0.35
    return 0.5


def household_burden(attrs: dict[str, Any], inc: float) -> float:
    size = parse_numeric(attrs.get("household_size")) or 2.5
    children = parse_numeric(attrs.get("children_count")) or 0.0
    elderly = parse_numeric(attrs.get("elderly_dependents")) or 0.0
    size_component = clamp((size - 1.0) / 5.0)
    dependent_component = clamp((children + elderly) / 4.0)
    return clamp(0.45 * size_component + 0.35 * dependent_component + 0.2 * (1.0 - inc))


def digital_score(attrs: dict[str, Any], edu: float, urb: float, key: str) -> float:
    raw_access = norm(attrs.get("digital_access_level") or attrs.get("computer_literacy"))
    raw_frequency = norm(attrs.get("internet_frequency") or attrs.get("internet_use"))
    age = age_midpoint(attrs)
    age_component = 0.55 if age is None else clamp(1.15 - age / 80.0)
    base = 0.45 * edu + 0.25 * urb + 0.30 * age_component
    if any(token in raw_access for token in ("high", "literate", "advanced")):
        base += 0.16
    if any(token in raw_access for token in ("partial", "medium", "basic")):
        base += 0.05
    if any(token in raw_access for token in ("illiterate", "none", "low")):
        base -= 0.18
    if any(token in raw_frequency for token in ("daily", "frequent", "always")):
        base += 0.12
    if any(token in raw_frequency for token in ("rare", "never")):
        base -= 0.2
    return clamp(base + stable_noise(key + ":digital"))


def category_affordability(attrs: dict[str, Any], inc: float, pressure: float, category_price_index: float, key: str) -> float:
    base = 0.58 * inc + 0.22 * (1.0 - pressure) + 0.2 * (1.0 - category_price_index)
    return clamp(base + stable_noise(key + ":affordability", 0.03))


def expand_record(record: dict[str, Any], *, category: str, category_price_index: float) -> dict[str, Any]:
    attrs = hard(record)
    key = persona_key(record)

    inc = income_score(attrs)
    edu = education_score(attrs)
    urb = urban_score(attrs)
    emp_pressure = employment_pressure(attrs)
    h_burden = household_burden(attrs, inc)
    budget_pressure = clamp(0.46 * (1.0 - inc) + 0.32 * h_burden + 0.22 * emp_pressure + stable_noise(key + ":budget", 0.025))
    digital = digital_score(attrs, edu, urb, key)
    risk_aversion = clamp(0.35 * budget_pressure + 0.25 * h_burden + 0.2 * (1.0 - digital) + 0.2 * employment_pressure(attrs) + stable_noise(key + ":risk", 0.035))
    price_sensitivity = clamp(0.5 * budget_pressure + 0.25 * (1.0 - inc) + 0.15 * h_burden + 0.1 * category_price_index + stable_noise(key + ":price", 0.035))
    brand_openness = clamp(0.36 * edu + 0.28 * digital + 0.18 * urb + 0.18 * inc + stable_noise(key + ":brand", 0.04))
    review_dependency = clamp(0.48 * digital + 0.23 * risk_aversion + 0.17 * category_price_index + 0.12 * edu + stable_noise(key + ":review", 0.035))
    warranty_sensitivity = clamp(0.48 * risk_aversion + 0.22 * category_price_index + 0.18 * budget_pressure + 0.12 * (1.0 - inc) + stable_noise(key + ":warranty", 0.03))
    discount_responsiveness = clamp(0.55 * price_sensitivity + 0.25 * budget_pressure + 0.2 * (1.0 - inc) + stable_noise(key + ":discount", 0.025))
    novelty_seeking = clamp(0.36 * digital + 0.25 * brand_openness + 0.2 * edu + 0.19 * (1.0 - risk_aversion) + stable_noise(key + ":novelty", 0.04))
    online_purchase_readiness = clamp(0.68 * digital + 0.18 * urb + 0.14 * inc + stable_noise(key + ":online", 0.035))
    offline_store_reliance = clamp(0.5 * (1.0 - digital) + 0.25 * (1.0 - urb) + 0.25 * risk_aversion + stable_noise(key + ":offline", 0.03))
    affordability = category_affordability(attrs, inc, budget_pressure, category_price_index, key)

    media_habits = {
        "digital_intensity": round_score(digital),
        "tv_usage": round_score(0.55 * (1.0 - digital) + 0.25 * risk_aversion + 0.2 * (1.0 - edu)),
        "social_media_usage": round_score(0.72 * digital + 0.18 * novelty_seeking + 0.1 * urb),
        "youtube_usage": round_score(0.66 * digital + 0.2 * review_dependency + 0.14 * edu),
        "online_reviews_usage": round_score(review_dependency),
        "offline_word_of_mouth": round_score(0.4 * offline_store_reliance + 0.28 * risk_aversion + 0.32 * h_burden),
    }

    shopping_habits = {
        "online_purchase_readiness": round_score(online_purchase_readiness),
        "offline_store_reliance": round_score(offline_store_reliance),
        "price_comparison": round_score(0.45 * price_sensitivity + 0.33 * review_dependency + 0.22 * digital),
        "discount_responsiveness": round_score(discount_responsiveness),
        "installment_preference": round_score(0.38 * budget_pressure + 0.34 * category_price_index + 0.28 * (1.0 - inc)),
        "brand_switching_readiness": round_score(0.42 * discount_responsiveness + 0.3 * novelty_seeking + 0.28 * (1.0 - brand_openness)),
    }

    psychographics = {
        "budget_pressure": round_score(budget_pressure),
        "household_burden": round_score(h_burden),
        "price_sensitivity": round_score(price_sensitivity),
        "risk_aversion": round_score(risk_aversion),
        "brand_openness": round_score(brand_openness),
        "review_dependency": round_score(review_dependency),
        "warranty_sensitivity": round_score(warranty_sensitivity),
        "novelty_seeking": round_score(novelty_seeking),
        "durability_preference": round_score(0.45 * risk_aversion + 0.35 * warranty_sensitivity + 0.2 * price_sensitivity),
    }

    category_priors = {
        "category": category,
        "category_price_index": round_score(category_price_index),
        "category_affordability": round_score(affordability),
        "need_activation": round_score(0.34 * affordability + 0.24 * h_burden + 0.22 * digital + 0.2 * (1.0 - risk_aversion)),
        "comfortable_price_multiplier": round(0.72 + 0.56 * affordability - 0.2 * price_sensitivity, 4),
        "stretch_price_multiplier": round(0.92 + 0.66 * affordability - 0.16 * risk_aversion, 4),
        "main_barrier_prior": infer_barrier(price_sensitivity, risk_aversion, digital, affordability),
    }

    soft = record.get("soft") if isinstance(record.get("soft"), dict) else {}
    soft.update(
        {
            "media_habits": media_habits,
            "shopping_habits": shopping_habits,
            "psychographics": psychographics,
            "category_priors": category_priors,
            "soft_trait_trace": {
                "version": SOFT_TRAIT_VERSION,
                "method": "deterministic_conditional_priors",
                "evidence_level": "model_inferred_from_hard_fields",
                "inputs_used": sorted(attrs.keys()),
                "ruleset": "income_education_digital_household_budget_v0_1",
                "llm_generated": False,
                "limitations": [
                    "Soft traits are priors, not observed survey responses.",
                    "Use for simulation initialization, not factual claims about individuals.",
                    "Calibrate against surveys, sales, click, or CBC data before decision-grade reporting.",
                ],
            },
        }
    )

    enriched = dict(record)
    enriched["soft"] = soft
    enriched["persona_stage"] = "soft_trait_enriched_skeleton"
    trace = enriched.get("calibration_trace") if isinstance(enriched.get("calibration_trace"), dict) else {}
    trace["soft_trait_expansion"] = soft["soft_trait_trace"]
    enriched["calibration_trace"] = trace
    return enriched


def infer_barrier(price_sensitivity: float, risk_aversion: float, digital: float, affordability: float) -> str:
    scores = {
        "price": price_sensitivity + (1.0 - affordability),
        "risk_or_warranty": risk_aversion,
        "information_gap": 1.0 - digital,
        "no_major_barrier": affordability * (1.0 - risk_aversion),
    }
    return max(scores.items(), key=lambda item: item[1])[0]


def audit(records: list[dict[str, Any]], category: str, category_price_index: float) -> dict[str, Any]:
    field_counts: Counter[str] = Counter()
    barrier_counts: Counter[str] = Counter()
    sums: dict[str, float] = Counter()
    n = 0
    for record in records:
        soft = record.get("soft", {})
        if not isinstance(soft, dict):
            continue
        for section in ("media_habits", "shopping_habits", "psychographics", "category_priors"):
            if isinstance(soft.get(section), dict):
                field_counts[section] += len(soft[section])
        psych = soft.get("psychographics", {}) if isinstance(soft.get("psychographics"), dict) else {}
        media = soft.get("media_habits", {}) if isinstance(soft.get("media_habits"), dict) else {}
        cat = soft.get("category_priors", {}) if isinstance(soft.get("category_priors"), dict) else {}
        for key in ("price_sensitivity", "risk_aversion", "budget_pressure", "review_dependency"):
            if isinstance(psych.get(key), (int, float)):
                sums[key] += float(psych[key])
        if isinstance(media.get("digital_intensity"), (int, float)):
            sums["digital_intensity"] += float(media["digital_intensity"])
        if isinstance(cat.get("category_affordability"), (int, float)):
            sums["category_affordability"] += float(cat["category_affordability"])
        barrier = cat.get("main_barrier_prior")
        if isinstance(barrier, str):
            barrier_counts[barrier] += 1
        n += 1
    means = {key: round(value / n, 4) for key, value in sums.items()} if n else {}
    return {
        "record_count": n,
        "category": category,
        "category_price_index": category_price_index,
        "soft_trait_version": SOFT_TRAIT_VERSION,
        "method": "deterministic_conditional_priors",
        "llm_generated": False,
        "mean_scores": means,
        "barrier_counts": dict(barrier_counts),
        "section_field_counts_total": dict(field_counts),
        "limitations": [
            "Soft traits are inferred priors and must not be represented as observed consumer facts.",
            "Decision-grade pricing requires survey, sales, clickstream, or CBC calibration.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("personas_core", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--category", default="generic_consumer_product")
    parser.add_argument(
        "--category-price-index",
        type=float,
        default=0.5,
        help="0=cheap category, 1=expensive category relative to household budget.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.category_price_index <= 1.0:
        raise ValueError("--category-price-index must be between 0 and 1")
    records = load_jsonl(args.personas_core)
    enriched = [expand_record(record, category=args.category, category_price_index=args.category_price_index) for record in records]
    write_jsonl(args.output, enriched)
    summary = audit(enriched, args.category, args.category_price_index)
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
