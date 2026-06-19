#!/usr/bin/env python3
"""Create a country scenario pipeline config.

This is a configuration builder, not a runner. It makes the intended product
workflow explicit:

country pack + product scenario + margins + dimensions
→ a new run config that regenerates a weighted panel for that country.

It never points the pipeline at a checked-in persona panel or a previous
choice-results file.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PANEL_SIZE = 10_000
DEFAULT_MEDIUM_SAMPLE_SIZE = 1_000
DEFAULT_DEEP_SAMPLE_SIZE = 100
ALLOWED_INTERVIEW_ENGINES = {"rule_based_baseline", "llm_short_all"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "scenario"


def parse_dimension(value: str) -> tuple[str, list[str]]:
    if "=" not in value:
        raise ValueError(f"dimension must use FIELD=value1,value2 syntax: {value!r}")
    field, raw_values = value.split("=", 1)
    field = field.strip()
    values = [item.strip() for item in raw_values.split(",") if item.strip()]
    if not field or not values:
        raise ValueError(f"invalid dimension: {value!r}")
    return field, values


def parse_dimensions(values: list[str], dimension_json: Path | None) -> dict[str, list[str]]:
    dimensions: dict[str, list[str]] = {}
    if dimension_json is not None:
        loaded = load_json(dimension_json)
        for key, value in loaded.items():
            if not isinstance(key, str) or not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                raise ValueError(f"dimension_json contains invalid dimension {key!r}")
            dimensions[key] = value
    for item in values:
        field, parsed_values = parse_dimension(item)
        dimensions[field] = parsed_values
    if not dimensions:
        raise ValueError("at least one dimension is required; use --dimension or --dimension-json")
    return dimensions


def scenario_category(product_scenario: dict[str, Any], fallback: str | None) -> str:
    value = fallback or product_scenario.get("category") or product_scenario.get("product_category")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("category is required when product scenario does not contain one")
    return value.strip()


def default_run_id(country_pack: dict[str, Any], product_scenario_path: Path, category: str) -> str:
    identity = country_pack.get("country_identity", {}) if isinstance(country_pack.get("country_identity"), dict) else {}
    iso2 = identity.get("iso2") or identity.get("iso3") or identity.get("country_name") or "country"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{slugify(str(iso2))}_{slugify(category)}_{slugify(product_scenario_path.stem)}_{timestamp}"


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    country_pack = load_json(args.country_pack)
    product_scenario = load_json(args.product_scenario)
    category = scenario_category(product_scenario, args.category)
    run_id = args.run_id or default_run_id(country_pack, args.product_scenario, category)
    dimensions = parse_dimensions(args.dimension, args.dimension_json)

    if args.interview_engine not in ALLOWED_INTERVIEW_ENGINES:
        raise ValueError(f"interview_engine must be one of {sorted(ALLOWED_INTERVIEW_ENGINES)}")
    if args.sample_size <= 0:
        raise ValueError("--sample-size must be positive")
    if args.medium_sample_size <= 0 or args.deep_sample_size <= 0:
        raise ValueError("sample layer sizes must be positive")
    if args.deep_sample_size > args.medium_sample_size:
        raise ValueError("deep sample size should not exceed medium sample size")

    config: dict[str, Any] = {
        "run_id": run_id,
        "country_pack": str(args.country_pack),
        "dimensions": dimensions,
        "sample_size": args.sample_size,
        "product_scenario": str(args.product_scenario),
        "category": category,
        "category_price_index": args.category_price_index,
        "interview_engine": args.interview_engine,
        "ipf_iterations": args.ipf_iterations,
        "ipf_tolerance": args.ipf_tolerance,
        "bootstrap_iterations": args.bootstrap_iterations,
        "bootstrap_seed": args.bootstrap_seed,
        "generate_report": True,
        "report_max_reasons": args.report_max_reasons,
        "report_max_artifacts": args.report_max_artifacts,
        "generate_dashboard_data": True,
        "generate_dashboard_html": True,
        "dashboard_max_reasons": args.dashboard_max_reasons,
        "dashboard_max_artifacts": args.dashboard_max_artifacts,
        "dashboard_max_archetypes": args.dashboard_max_archetypes,
        "dashboard_max_segments": args.dashboard_max_segments,
        "dashboard_max_reason_segments": args.dashboard_max_reason_segments,
        "dashboard_min_segment_support": args.dashboard_min_segment_support,
        "dashboard_medium_sample_size": args.medium_sample_size,
        "dashboard_deep_sample_size": args.deep_sample_size,
        "validate_artifacts": True,
        "max_report_lines": 0,
        "country_run_policy": {
            "regenerate_panel_from_country_pack": True,
            "no_static_persona_panel_input": True,
            "medium_and_deep_samples_derived_from_active_run": True,
        },
    }

    if args.margins is not None:
        config["margins"] = str(args.margins)
    elif args.margins_json is not None:
        config["margins_inline"] = load_json(args.margins_json)
    else:
        raise ValueError("one of --margins or --margins-json is required")

    if args.interview_engine == "rule_based_baseline":
        config["choice_mode"] = args.choice_mode
        config["choice_temperature"] = args.choice_temperature
    else:
        config.update(
            {
                "llm_order_policy": args.llm_order_policy,
                "llm_prompt_variant": args.llm_prompt_variant,
                "include_story_in_llm_prompt": args.include_story_in_llm_prompt,
                "max_story_chars": args.max_story_chars,
                "validate_llm_choice_quality": True,
                "llm_quality_subgroup_fields": args.llm_quality_subgroup_fields,
            }
        )
        if args.llm_prompt_limit is not None:
            config["llm_prompt_limit"] = args.llm_prompt_limit
        if args.llm_response_file is not None:
            config["llm_response_file"] = str(args.llm_response_file)
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-pack", type=Path, required=True)
    parser.add_argument("--product-scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--category")
    parser.add_argument("--category-price-index", type=float, default=0.5)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_PANEL_SIZE)
    parser.add_argument("--medium-sample-size", type=int, default=DEFAULT_MEDIUM_SAMPLE_SIZE)
    parser.add_argument("--deep-sample-size", type=int, default=DEFAULT_DEEP_SAMPLE_SIZE)
    parser.add_argument("--dimension", action="append", default=[], help="FIELD=value1,value2. Can be repeated.")
    parser.add_argument("--dimension-json", type=Path)
    parser.add_argument("--margins", type=Path)
    parser.add_argument("--margins-json", type=Path)
    parser.add_argument("--interview-engine", choices=sorted(ALLOWED_INTERVIEW_ENGINES), default="llm_short_all")
    parser.add_argument("--choice-mode", default="argmax")
    parser.add_argument("--choice-temperature", type=float, default=0.35)
    parser.add_argument("--llm-order-policy", choices=["canonical", "reverse", "rotate"], default="rotate")
    parser.add_argument("--llm-prompt-variant", choices=["neutral", "tradeoff"], default="tradeoff")
    parser.add_argument("--llm-prompt-limit", type=int)
    parser.add_argument("--llm-response-file", type=Path)
    parser.add_argument("--include-story-in-llm-prompt", action="store_true")
    parser.add_argument("--max-story-chars", type=int, default=900)
    parser.add_argument("--llm-quality-subgroup-fields", default="region,sex,education_level,income_decile,settlement_type,employment_status")
    parser.add_argument("--ipf-iterations", type=int, default=200)
    parser.add_argument("--ipf-tolerance", type=float, default=1e-6)
    parser.add_argument("--bootstrap-iterations", type=int, default=120)
    parser.add_argument("--bootstrap-seed", type=int, default=20260618)
    parser.add_argument("--report-max-reasons", type=int, default=5)
    parser.add_argument("--report-max-artifacts", type=int, default=18)
    parser.add_argument("--dashboard-max-reasons", type=int, default=12)
    parser.add_argument("--dashboard-max-artifacts", type=int, default=40)
    parser.add_argument("--dashboard-max-archetypes", type=int, default=8)
    parser.add_argument("--dashboard-max-segments", type=int, default=250)
    parser.add_argument("--dashboard-max-reason-segments", type=int, default=80)
    parser.add_argument("--dashboard-min-segment-support", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = build_config(args)
    write_json(args.output, config)
    print(json.dumps({"run_id": config["run_id"], "output": str(args.output), "sample_size": config["sample_size"], "interview_engine": config["interview_engine"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
