#!/usr/bin/env python3
"""Run a deterministic rule-based discrete choice baseline.

Inputs:
- enriched personas JSONL from `expand_soft_traits.py`
- normalized choice scenario JSON from `product_scenario_normalizer.py`

Output:
- choice_results.jsonl compatible with `validate_choice_interviews.py`
- audit JSON with aggregate counts and method limitations

This is a transparent random-utility-style baseline. It is not calibrated to
real survey, sales, click, or CBC data and must not be represented as a real
market forecast.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CHOICE_MODEL_VERSION = "0.1.0"


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
        raise ValueError("personas file is empty")
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


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


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def stable_noise(key: str, scale: float = 0.025) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    raw = int(digest[:12], 16) / float(16**12 - 1)
    return (raw - 0.5) * 2.0 * scale


def soft_section(persona: dict[str, Any], section: str) -> dict[str, Any]:
    soft = persona.get("soft")
    if not isinstance(soft, dict):
        return {}
    value = soft.get(section)
    return value if isinstance(value, dict) else {}


def score(persona: dict[str, Any], section: str, field: str, default: float = 0.5) -> float:
    return clamp(numeric(soft_section(persona, section).get(field), default))


def ensure_scenario(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives = scenario.get("alternatives")
    if not isinstance(alternatives, list) or len(alternatives) < 2:
        raise ValueError("normalized scenario must contain at least two alternatives")
    cleaned: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in alternatives:
        if not isinstance(item, dict):
            raise ValueError("alternative must be an object")
        alt_id = item.get("id")
        if not isinstance(alt_id, str) or not alt_id:
            raise ValueError("alternative id must be a non-empty string")
        if alt_id in ids:
            raise ValueError(f"duplicate alternative id: {alt_id}")
        ids.add(alt_id)
        attrs = item.get("normalized_attributes")
        if not isinstance(attrs, dict):
            raise ValueError(f"alternative {alt_id}: missing normalized_attributes")
        cleaned.append(item)
    if not any(item.get("is_outside_option") is True for item in cleaned):
        raise ValueError("normalized scenario must include an outside option")
    return cleaned


def alternative_value(alternative: dict[str, Any], field: str, default: float = 0.0) -> float:
    attrs = alternative.get("normalized_attributes") if isinstance(alternative.get("normalized_attributes"), dict) else {}
    return clamp(numeric(attrs.get(field), default))


def utility(persona: dict[str, Any], alternative: dict[str, Any], *, scale: float) -> tuple[float, dict[str, float]]:
    pid = str(persona.get("persona_id"))
    alt_id = str(alternative.get("id"))
    outside = alternative.get("is_outside_option") is True

    price_sensitivity = score(persona, "psychographics", "price_sensitivity")
    brand_openness = score(persona, "psychographics", "brand_openness")
    warranty_sensitivity = score(persona, "psychographics", "warranty_sensitivity")
    review_dependency = score(persona, "psychographics", "review_dependency")
    risk_aversion = score(persona, "psychographics", "risk_aversion")
    budget_pressure = score(persona, "psychographics", "budget_pressure")
    affordability = score(persona, "category_priors", "category_affordability")
    need_activation = score(persona, "category_priors", "need_activation")
    online_readiness = score(persona, "shopping_habits", "online_purchase_readiness")

    price_index = alternative_value(alternative, "price_index")
    brand_strength = alternative_value(alternative, "brand_strength")
    feature_score = alternative_value(alternative, "feature_score")
    warranty_score = alternative_value(alternative, "warranty_score")
    risk_score = alternative_value(alternative, "risk_score")

    if outside:
        outside_utility = (
            0.85 * budget_pressure
            + 0.65 * (1.0 - need_activation)
            + 0.45 * risk_aversion
            + 0.25 * (1.0 - affordability)
            + stable_noise(pid + ":" + alt_id, 0.035)
        )
        return scale * outside_utility, {
            "outside_budget_pressure": budget_pressure,
            "outside_low_need": 1.0 - need_activation,
            "outside_risk_aversion": risk_aversion,
        }

    components = {
        "price_fit": -1.25 * price_sensitivity * price_index,
        "brand_fit": 0.78 * brand_openness * brand_strength,
        "warranty_fit": 0.62 * warranty_sensitivity * warranty_score,
        "feature_fit": 0.58 * review_dependency * feature_score,
        "risk_penalty": -0.85 * risk_aversion * risk_score,
        "affordability_fit": 0.72 * affordability * (1.0 - price_index),
        "need_fit": 0.42 * need_activation,
        "digital_channel_fit": 0.18 * online_readiness,
        "idiosyncratic_noise": stable_noise(pid + ":" + alt_id, 0.035),
    }
    return scale * sum(components.values()), components


def softmax(values: dict[str, float], temperature: float) -> dict[str, float]:
    if temperature <= 0:
        winner = max(values.items(), key=lambda item: (item[1], item[0]))[0]
        return {key: 1.0 if key == winner else 0.0 for key in values}
    max_value = max(values.values())
    exp_values = {key: math.exp((value - max_value) / temperature) for key, value in values.items()}
    total = sum(exp_values.values())
    return {key: value / total for key, value in exp_values.items()}


def choose_from_probabilities(probabilities: dict[str, float], key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    threshold = int(digest[:12], 16) / float(16**12 - 1)
    cumulative = 0.0
    for alt_id, probability in sorted(probabilities.items()):
        cumulative += probability
        if threshold <= cumulative:
            return alt_id
    return max(probabilities.items(), key=lambda item: item[1])[0]


def reason_codes(chosen_alt: dict[str, Any], components: dict[str, float]) -> tuple[list[str], list[str], list[str]]:
    if chosen_alt.get("is_outside_option") is True:
        drivers = []
        if components.get("outside_budget_pressure", 0) > 0.55:
            drivers.append("budget_pressure")
        if components.get("outside_low_need", 0) > 0.45:
            drivers.append("low_need_activation")
        if components.get("outside_risk_aversion", 0) > 0.55:
            drivers.append("risk_aversion")
        return drivers or ["delay_or_no_purchase"], ["no_product_selected"], ["lower price", "stronger need", "lower perceived risk"]

    positive = sorted(((key, value) for key, value in components.items() if value > 0), key=lambda item: item[1], reverse=True)
    negative = sorted(((key, value) for key, value in components.items() if value < 0), key=lambda item: item[1])
    drivers = [key for key, _ in positive[:3]] or ["relative_utility"]
    barriers = [key for key, _ in negative[:3]] or ["no_major_barrier"]
    switches = []
    if "price_fit" in barriers or "affordability_fit" not in drivers:
        switches.append("lower price")
    if "risk_penalty" in barriers:
        switches.append("lower perceived risk")
    if "warranty_fit" not in drivers:
        switches.append("better warranty")
    if "feature_fit" not in drivers:
        switches.append("stronger feature evidence")
    return drivers, barriers, switches[:4] or ["materially better value proposition"]


def confidence_from_gap(sorted_utilities: list[tuple[str, float]]) -> str:
    if len(sorted_utilities) < 2:
        return "low"
    gap = sorted_utilities[0][1] - sorted_utilities[1][1]
    if gap >= 0.45:
        return "high"
    if gap >= 0.18:
        return "medium"
    return "low"


def interview_response(choice_name: str, drivers: list[str], barriers: list[str], confidence: str) -> str:
    driver_text = ", ".join(drivers[:3])
    barrier_text = ", ".join(barriers[:2])
    return (
        f"I would choose {choice_name} in this scenario. The main reasons are {driver_text}. "
        f"The main reservations are {barrier_text}. My confidence is {confidence} because this is a model-inferred baseline, not an observed human interview."
    )


def output_choice_label(chosen_alt: dict[str, Any], alternatives: list[dict[str, Any]]) -> str:
    if chosen_alt.get("is_outside_option") is True:
        return "none_or_delay"
    non_outside = [alt for alt in alternatives if alt.get("is_outside_option") is not True]
    if non_outside and chosen_alt.get("id") == non_outside[0].get("id"):
        return "focal_product"
    return "competitor"


def run_choices(personas: list[dict[str, Any]], scenario: dict[str, Any], *, mode: str, temperature: float, scale: float) -> list[dict[str, Any]]:
    alternatives = ensure_scenario(scenario)
    by_id = {str(item["id"]): item for item in alternatives}
    results: list[dict[str, Any]] = []
    for persona in personas:
        pid = str(persona.get("persona_id"))
        if not pid:
            raise ValueError(f"line {persona.get('_line_number')}: missing persona_id")
        weight = numeric(persona.get("population_weight"), -1.0)
        if weight <= 0:
            raise ValueError(f"persona {pid}: invalid population_weight")
        utility_by_alt: dict[str, float] = {}
        components_by_alt: dict[str, dict[str, float]] = {}
        for alternative in alternatives:
            alt_id = str(alternative["id"])
            util, components = utility(persona, alternative, scale=scale)
            utility_by_alt[alt_id] = util
            components_by_alt[alt_id] = components

        if mode == "argmax":
            chosen_id = max(utility_by_alt.items(), key=lambda item: (item[1], item[0]))[0]
            probabilities = softmax(utility_by_alt, temperature=0.35)
        elif mode == "softmax_sample":
            probabilities = softmax(utility_by_alt, temperature=temperature)
            chosen_id = choose_from_probabilities(probabilities, pid + ":choice")
        else:
            raise ValueError(f"unsupported mode: {mode}")

        sorted_utils = sorted(utility_by_alt.items(), key=lambda item: item[1], reverse=True)
        chosen_alt = by_id[chosen_id]
        drivers, barriers, switches = reason_codes(chosen_alt, components_by_alt[chosen_id])
        confidence = confidence_from_gap(sorted_utils)
        choice_label = output_choice_label(chosen_alt, alternatives)
        response = interview_response(str(chosen_alt.get("name") or chosen_id), drivers, barriers, confidence)
        results.append(
            {
                "persona_id": pid,
                "population_weight": weight,
                "choice": choice_label,
                "chosen_alternative_id": chosen_id,
                "chosen_alternative_name": chosen_alt.get("name"),
                "interview_response": response,
                "main_drivers": drivers,
                "main_barriers": barriers,
                "switch_conditions": switches,
                "answer_confidence": confidence,
                "choice_reason_codes": drivers,
                "diagnostics": {
                    "utilities": {key: round(value, 6) for key, value in utility_by_alt.items()},
                    "softmax_probabilities_for_diagnostics_only": {key: round(value, 6) for key, value in probabilities.items()},
                    "utility_gap_top2": round(sorted_utils[0][1] - sorted_utils[1][1], 6) if len(sorted_utils) > 1 else None,
                },
                "isolation": {
                    "context_scope": "single_persona",
                    "saw_other_answers": False,
                    "saw_aggregate_results": False,
                    "saw_target_proportion": False,
                },
                "generation_controls": {
                    "method": "deterministic_rule_based_random_utility_baseline",
                    "model": "none",
                    "temperature": temperature if mode == "softmax_sample" else 0.0,
                    "seed": hashlib.sha256((pid + ":choice").encode("utf-8")).hexdigest()[:16],
                    "choice_model_version": CHOICE_MODEL_VERSION,
                },
                "quality_controls": {
                    "llm_generated": False,
                    "score_only": False,
                    "discrete_choice_record": True,
                    "probabilities_are_diagnostics_only": True,
                    "calibration_level": "uncalibrated_rule_based_baseline",
                },
            }
        )
    return results


def audit(results: list[dict[str, Any]], scenario: dict[str, Any], mode: str) -> dict[str, Any]:
    choice_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    weighted: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    for row in results:
        choice = str(row.get("choice"))
        weight = numeric(row.get("population_weight"))
        choice_counts[choice] += 1
        confidence_counts[str(row.get("answer_confidence"))] += 1
        weighted[choice] += weight
        total_weight += weight
    shares = {key: value / total_weight for key, value in weighted.items()} if total_weight else {}
    return {
        "record_count": len(results),
        "scenario_id": scenario.get("scenario_id"),
        "category": scenario.get("category"),
        "choice_model_version": CHOICE_MODEL_VERSION,
        "method": "deterministic_rule_based_random_utility_baseline",
        "mode": mode,
        "choice_counts": dict(choice_counts),
        "confidence_counts": dict(confidence_counts),
        "weighted_choice_shares": {key: round(value, 6) for key, value in shares.items()},
        "total_weight": total_weight,
        "limitations": [
            "This is an uncalibrated rule-based baseline, not a real market forecast.",
            "Utilities are constructed from inferred soft traits and normalized product attributes.",
            "Diagnostics probabilities are not person-level final answers.",
            "Replace or calibrate coefficients with CBC, survey, sales, click, or experiment data before decision-grade use.",
            "Standard logit-style baselines may impose unrealistic substitution patterns; test nested or mixed-logit variants when calibrated data exists.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("personas_enriched", type=Path)
    parser.add_argument("normalized_choice_scenario", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--mode", choices=["argmax", "softmax_sample"], default="argmax")
    parser.add_argument("--temperature", type=float, default=0.35)
    parser.add_argument("--utility-scale", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.temperature <= 0 and args.mode == "softmax_sample":
        raise ValueError("--temperature must be positive in softmax_sample mode")
    personas = load_jsonl(args.personas_enriched)
    scenario = load_json(args.normalized_choice_scenario)
    results = run_choices(personas, scenario, mode=args.mode, temperature=args.temperature, scale=args.utility_scale)
    write_jsonl(args.output, results)
    summary = audit(results, scenario, args.mode)
    if args.audit:
        write_json(args.audit, summary)
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
