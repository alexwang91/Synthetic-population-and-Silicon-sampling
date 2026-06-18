#!/usr/bin/env python3
"""Normalize product inputs into an auditable discrete-choice scenario.

This script constructs a finite choice set for later rule-based or LLM-based
choice simulation. It does not predict choices and does not estimate utilities.

Input accepts either:
{
  "scenario_id": "smartwatch_demo",
  "category": "smartwatch",
  "currency": "EUR",
  "alternatives": [{...}]
}

or the legacy alias:
{
  "products": [{...}]
}

Each alternative should include at least `name` and should include `price`
unless it is explicitly marked as an outside option. Numeric fields such as
brand_strength, feature_score, warranty_score, and risk_score may be supplied;
otherwise transparent heuristics are used and marked in the audit trace.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


NORMALIZER_VERSION = "0.1.0"
OUTSIDE_IDS = {"none", "no_choice", "delay", "outside", "opt_out"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("scenario must be a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def slug(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered or "alternative"


def as_float(value: Any, *, default: float | None = None) -> float | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match:
            return float(match.group(0))
    return default


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def score(value: float) -> float:
    return round(clamp(value), 4)


def parse_warranty_years(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).lower()
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    number = numbers[0]
    if "month" in text or "mo" in text:
        return number / 12.0
    return number


def warranty_score_from_years(years: float | None) -> tuple[float, str]:
    if years is None:
        return 0.5, "default_missing_warranty"
    return score(years / 4.0), "parsed_warranty_years"


def feature_count(item: dict[str, Any]) -> int:
    features = item.get("features") or item.get("main_features")
    attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    if not features and isinstance(attributes, dict):
        features = attributes.get("features") or attributes.get("main_features")
    if isinstance(features, list):
        return len([feature for feature in features if str(feature).strip()])
    if isinstance(features, str) and features.strip():
        return len([part for part in re.split(r"[,;|]", features) if part.strip()])
    return 0


def supplied_score(item: dict[str, Any], field: str) -> float | None:
    value = as_float(item.get(field))
    if value is None:
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        value = as_float(attrs.get(field)) if isinstance(attrs, dict) else None
    if value is None:
        return None
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    return clamp(value)


def normalize_price(price: float | None, min_price: float, max_price: float) -> float | None:
    if price is None:
        return None
    if max_price <= min_price:
        return 0.5
    return score((price - min_price) / (max_price - min_price))


def normalize_feature_score(item: dict[str, Any], max_feature_count: int) -> tuple[float, str]:
    explicit = supplied_score(item, "feature_score")
    if explicit is not None:
        return score(explicit), "provided_feature_score"
    count = feature_count(item)
    if max_feature_count <= 0:
        return 0.5, "default_missing_features"
    return score(0.35 + 0.65 * (count / max_feature_count)), "feature_count_relative"


def normalize_brand_strength(item: dict[str, Any]) -> tuple[float, str]:
    explicit = supplied_score(item, "brand_strength")
    if explicit is not None:
        return score(explicit), "provided_brand_strength"
    brand = str(item.get("brand") or item.get("attributes", {}).get("brand") if isinstance(item.get("attributes"), dict) else "")
    name = str(item.get("name") or "")
    known_premium = ["apple", "samsung", "sony", "bosch", "miele", "dyson", "xiaomi", "huawei", "lg", "panasonic"]
    text = f"{brand} {name}".lower()
    if any(token in text for token in known_premium):
        return 0.72, "brand_keyword_prior"
    if brand.strip():
        return 0.58, "brand_present_default"
    return 0.5, "default_missing_brand"


def normalize_risk_score(brand_strength: float, warranty_score: float, item: dict[str, Any]) -> tuple[float, str]:
    explicit = supplied_score(item, "risk_score")
    if explicit is not None:
        return score(explicit), "provided_risk_score"
    return score(1.0 - (0.58 * brand_strength + 0.42 * warranty_score)), "derived_from_brand_and_warranty"


def is_outside_option(item: dict[str, Any]) -> bool:
    raw_id = str(item.get("id") or "").strip().lower()
    raw_name = str(item.get("name") or "").strip().lower()
    if item.get("is_outside_option") is True:
        return True
    if raw_id in OUTSIDE_IDS:
        return True
    return any(token in raw_name for token in ("none", "delay", "no purchase", "not buy", "outside"))


def get_alternatives(raw: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives = raw.get("alternatives", raw.get("products"))
    if not isinstance(alternatives, list) or not alternatives:
        raise ValueError("scenario must contain a non-empty alternatives or products array")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(alternatives, 1):
        if not isinstance(item, dict):
            raise ValueError(f"alternative {index}: expected object")
        result.append(item)
    return result


def ensure_outside_option(alternatives: list[dict[str, Any]], include_outside: bool) -> list[dict[str, Any]]:
    if not include_outside:
        return alternatives
    if any(is_outside_option(item) for item in alternatives):
        return alternatives
    return [*alternatives, {"id": "none", "name": "None / delay purchase", "is_outside_option": True}]


def normalize_scenario(raw: dict[str, Any], *, include_outside: bool) -> dict[str, Any]:
    scenario_id = str(raw.get("scenario_id") or raw.get("id") or slug(str(raw.get("category") or "scenario")))
    category = str(raw.get("category") or raw.get("product_category") or "generic_consumer_product")
    currency = str(raw.get("currency") or "")
    alternatives_raw = ensure_outside_option(get_alternatives(raw), include_outside)
    max_feature_count = max((feature_count(item) for item in alternatives_raw if not is_outside_option(item)), default=0)
    prices = [as_float(item.get("price")) for item in alternatives_raw if not is_outside_option(item)]
    numeric_prices = [price for price in prices if price is not None and price >= 0]
    if not numeric_prices:
        raise ValueError("at least one non-outside alternative must have a non-negative price")
    min_price = min(numeric_prices)
    max_price = max(numeric_prices)

    normalized: list[dict[str, Any]] = []
    ids_seen: set[str] = set()
    warnings: list[str] = []
    evidence_notes: list[dict[str, Any]] = []

    for index, item in enumerate(alternatives_raw, 1):
        outside = is_outside_option(item)
        alt_id = str(item.get("id") or ("none" if outside else chr(64 + index))).strip()
        if not alt_id:
            alt_id = f"A{index}"
        if alt_id in ids_seen:
            raise ValueError(f"duplicate alternative id: {alt_id}")
        ids_seen.add(alt_id)
        name = str(item.get("name") or item.get("product_name") or alt_id).strip()
        if not name:
            raise ValueError(f"alternative {alt_id}: missing name")

        price = None if outside else as_float(item.get("price"))
        if not outside and (price is None or price < 0):
            raise ValueError(f"alternative {alt_id}: non-outside alternatives require non-negative price")

        if outside:
            normalized_attrs = {
                "price_index": 0.0,
                "brand_strength": 0.0,
                "feature_score": 0.0,
                "warranty_score": 0.0,
                "risk_score": 0.0,
                "outside_option_constant": 1.0,
            }
            evidence = {"outside_option": "explicit_or_inserted"}
        else:
            brand_strength, brand_method = normalize_brand_strength(item)
            feature_score, feature_method = normalize_feature_score(item, max_feature_count)
            years = parse_warranty_years(item.get("warranty") or (item.get("attributes", {}).get("warranty") if isinstance(item.get("attributes"), dict) else None))
            warranty_score, warranty_method = warranty_score_from_years(years)
            risk_score, risk_method = normalize_risk_score(brand_strength, warranty_score, item)
            normalized_attrs = {
                "price_index": normalize_price(price, min_price, max_price),
                "brand_strength": brand_strength,
                "feature_score": feature_score,
                "warranty_score": warranty_score,
                "risk_score": risk_score,
                "outside_option_constant": 0.0,
            }
            evidence = {
                "brand_strength": brand_method,
                "feature_score": feature_method,
                "warranty_score": warranty_method,
                "risk_score": risk_method,
            }

        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        output = {
            "id": alt_id,
            "name": name,
            "is_outside_option": outside,
            "price": price,
            "currency": currency,
            "raw_attributes": attrs,
            "normalized_attributes": normalized_attrs,
            "normalization_evidence": evidence,
        }
        if "brand" in item or (isinstance(attrs, dict) and "brand" in attrs):
            output["brand"] = item.get("brand", attrs.get("brand") if isinstance(attrs, dict) else None)
        if "warranty" in item or (isinstance(attrs, dict) and "warranty" in attrs):
            output["warranty"] = item.get("warranty", attrs.get("warranty") if isinstance(attrs, dict) else None)
        normalized.append(output)
        evidence_notes.append({"alternative_id": alt_id, "evidence": evidence})

    if not any(item["is_outside_option"] for item in normalized):
        warnings.append("No outside option included. Choice set may force purchase even when none/delay is realistic.")

    return {
        "scenario_id": scenario_id,
        "category": category,
        "currency": currency,
        "choice_task_type": "discrete_choice_cbc_style",
        "choice_set_policy": {
            "finite": True,
            "mutually_exclusive": True,
            "collectively_exhaustive": any(item["is_outside_option"] for item in normalized),
            "outside_option_included": any(item["is_outside_option"] for item in normalized),
        },
        "alternatives": normalized,
        "normalization_trace": {
            "version": NORMALIZER_VERSION,
            "method": "product_scenario_to_cbc_choice_set",
            "input_aliases_supported": ["alternatives", "products"],
            "price_range": {"min_price": min_price, "max_price": max_price},
            "evidence_notes": evidence_notes,
            "warnings": warnings,
            "limitations": [
                "Normalized attributes are preparation inputs for a choice model, not estimated utilities.",
                "Brand strength and feature scores should be replaced by client research or category benchmarks when available.",
                "Outside option should be included for realistic purchase/no-purchase simulation unless the task is intentionally forced choice.",
            ],
        },
    }


def validate_choice_scenario(scenario: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    alternatives = scenario.get("alternatives")
    if not isinstance(alternatives, list) or len(alternatives) < 2:
        errors.append("scenario must contain at least two alternatives after normalization")
        return errors
    ids = [item.get("id") for item in alternatives if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        errors.append("alternative ids must be unique")
    if not any(isinstance(item, dict) and item.get("is_outside_option") for item in alternatives):
        errors.append("scenario should include an outside option unless forced-choice is intentional")
    for item in alternatives:
        if not isinstance(item, dict):
            errors.append("alternative must be an object")
            continue
        attrs = item.get("normalized_attributes")
        if not isinstance(attrs, dict):
            errors.append(f"alternative {item.get('id')}: missing normalized_attributes")
            continue
        for field in ("price_index", "brand_strength", "feature_score", "warranty_score", "risk_score", "outside_option_constant"):
            value = attrs.get(field)
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                errors.append(f"alternative {item.get('id')}: {field} must be a number in [0,1]")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--no-outside-option", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw = load_json(args.scenario)
    normalized = normalize_scenario(raw, include_outside=not args.no_outside_option)
    errors = validate_choice_scenario(normalized)
    audit = {
        "scenario_id": normalized.get("scenario_id"),
        "category": normalized.get("category"),
        "alternative_count": len(normalized.get("alternatives", [])),
        "outside_option_included": normalized.get("choice_set_policy", {}).get("outside_option_included"),
        "error_count": len(errors),
        "errors": errors,
        "warnings": normalized.get("normalization_trace", {}).get("warnings", []),
        "passes_product_scenario_normalization": len(errors) == 0,
    }
    write_json(args.output, normalized)
    if args.audit:
        write_json(args.audit, audit)
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
