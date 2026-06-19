#!/usr/bin/env python3
"""Create and optionally run a country scenario pipeline config.

This command is the user-facing wrapper for the country-run workflow:

country inputs -> generated config -> dependency validation -> scenario pipeline

It never uses a prior persona panel or prior choice file as the population base.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PANEL_SIZE = 10_000
DEFAULT_MEDIUM_SAMPLE_SIZE = 1_000
DEFAULT_DEEP_SAMPLE_SIZE = 100
ALLOWED_INTERVIEW_ENGINES = {"rule_based_baseline", "llm_short_all"}
STOP_AFTER_CHOICES = [
    "validate_country_pack",
    "country_pack_to_cells",
    "run_ipf",
    "sample_persona_skeletons",
    "expand_soft_traits",
    "validate_persona_coherence",
    "product_scenario_normalizer",
    "run_choice_model",
    "export_llm_choice_prompts",
    "normalize_llm_choice_responses",
    "validate_choice_interviews",
    "validate_llm_choice_quality",
    "bootstrap_choice_intervals",
    "generate_market_report",
    "generate_dashboard_data",
    "validate_pipeline_artifacts",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def script_path(relative: str) -> Path:
    return repo_root() / relative


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "scenario"


def scenario_category(product_scenario: dict[str, Any], fallback: str | None) -> str:
    value = fallback or product_scenario.get("category") or product_scenario.get("product_category")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("category is required when product scenario does not contain one")
    return value.strip()


def default_run_id(country_pack_path: Path, product_scenario_path: Path, category: str) -> str:
    country_pack = load_json(country_pack_path)
    identity = country_pack.get("country_identity", {}) if isinstance(country_pack.get("country_identity"), dict) else {}
    iso2 = identity.get("iso2") or identity.get("iso3") or identity.get("country_name") or country_pack_path.stem
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{slugify(str(iso2))}_{slugify(category)}_{slugify(product_scenario_path.stem)}_{timestamp}"


def run(command: list[str], *, cwd: Path, step: str) -> dict[str, Any]:
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return {
        "step": step,
        "command": command,
        "returncode": process.returncode,
        "stdout_tail": process.stdout[-3000:],
        "stderr_tail": process.stderr[-3000:],
    }


def append_common_builder_args(command: list[str], args: argparse.Namespace) -> None:
    command.extend([
        "--country-pack", str(args.country_pack),
        "--product-scenario", str(args.product_scenario),
        "--output", str(args.config_output),
        "--run-id", args.run_id,
        "--category", args.category,
        "--category-price-index", str(args.category_price_index),
        "--sample-size", str(args.sample_size),
        "--medium-sample-size", str(args.medium_sample_size),
        "--deep-sample-size", str(args.deep_sample_size),
        "--interview-engine", args.interview_engine,
        "--ipf-iterations", str(args.ipf_iterations),
        "--ipf-tolerance", str(args.ipf_tolerance),
        "--bootstrap-iterations", str(args.bootstrap_iterations),
        "--bootstrap-seed", str(args.bootstrap_seed),
        "--report-max-reasons", str(args.report_max_reasons),
        "--report-max-artifacts", str(args.report_max_artifacts),
        "--dashboard-max-reasons", str(args.dashboard_max_reasons),
        "--dashboard-max-artifacts", str(args.dashboard_max_artifacts),
        "--dashboard-max-archetypes", str(args.dashboard_max_archetypes),
        "--dashboard-max-segments", str(args.dashboard_max_segments),
        "--dashboard-max-reason-segments", str(args.dashboard_max_reason_segments),
        "--dashboard-min-segment-support", str(args.dashboard_min_segment_support),
    ])
    for dimension in args.dimension:
        command.extend(["--dimension", dimension])
    if args.dimension_json:
        command.extend(["--dimension-json", str(args.dimension_json)])
    if args.margins:
        command.extend(["--margins", str(args.margins)])
    if args.margins_json:
        command.extend(["--margins-json", str(args.margins_json)])
    if args.interview_engine == "rule_based_baseline":
        command.extend(["--choice-mode", args.choice_mode, "--choice-temperature", str(args.choice_temperature)])
    else:
        command.extend([
            "--llm-order-policy", args.llm_order_policy,
            "--llm-prompt-variant", args.llm_prompt_variant,
            "--max-story-chars", str(args.max_story_chars),
            "--llm-quality-subgroup-fields", args.llm_quality_subgroup_fields,
        ])
        if args.llm_prompt_limit is not None:
            command.extend(["--llm-prompt-limit", str(args.llm_prompt_limit)])
        if args.llm_response_file is not None:
            command.extend(["--llm-response-file", str(args.llm_response_file)])
        if args.include_story_in_llm_prompt:
            command.append("--include-story-in-llm-prompt")


def run_country_scenario(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root()
    product = load_json(args.product_scenario)
    args.category = scenario_category(product, args.category)
    args.run_id = args.run_id or default_run_id(args.country_pack, args.product_scenario, args.category)
    if args.config_output is None:
        args.config_output = args.output_root / "_configs" / f"{args.run_id}.json"
    args.config_output.parent.mkdir(parents=True, exist_ok=True)

    builder_command = [sys.executable, str(script_path("skills/weighted-persona-pricing/scripts/create_country_scenario_config.py"))]
    append_common_builder_args(builder_command, args)
    builder_result = run(builder_command, cwd=root, step="create_country_scenario_config")
    if builder_result["returncode"] != 0:
        return {"status": "failed", "run_id": args.run_id, "results": [builder_result]}

    validator_command = [sys.executable, str(script_path("scripts/validate_no_static_panel_dependency.py")), str(args.config_output)]
    if args.country_run_audit:
        validator_command.extend(["--audit", str(args.country_run_audit)])
    validator_result = run(validator_command, cwd=root, step="validate_no_static_panel_dependency")
    if validator_result["returncode"] != 0:
        return {"status": "failed", "run_id": args.run_id, "config": str(args.config_output), "results": [builder_result, validator_result]}

    results = [builder_result, validator_result]
    if args.config_only:
        return {"status": "config_created", "run_id": args.run_id, "config": str(args.config_output), "results": results}

    pipeline_command = [
        sys.executable,
        str(script_path("skills/weighted-persona-pricing/scripts/run_scenario_pipeline.py")),
        str(args.config_output),
        "--output-root",
        str(args.output_root),
    ]
    if args.stop_after:
        pipeline_command.extend(["--stop-after", args.stop_after])
    pipeline_result = run(pipeline_command, cwd=root, step="run_scenario_pipeline")
    results.append(pipeline_result)
    manifest = args.output_root / args.run_id / "manifest.json"
    manifest_status = None
    if manifest.exists():
        manifest_status = load_json(manifest).get("status")
    status = "failed" if pipeline_result["returncode"] != 0 else (manifest_status or "passed")
    return {"status": status, "run_id": args.run_id, "config": str(args.config_output), "manifest": str(manifest), "manifest_status": manifest_status, "results": results}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-pack", type=Path, required=True)
    parser.add_argument("--product-scenario", type=Path, required=True)
    parser.add_argument("--margins", type=Path)
    parser.add_argument("--margins-json", type=Path)
    parser.add_argument("--dimension", action="append", default=[])
    parser.add_argument("--dimension-json", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("runs"))
    parser.add_argument("--config-output", type=Path)
    parser.add_argument("--country-run-audit", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--category")
    parser.add_argument("--category-price-index", type=float, default=0.5)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_PANEL_SIZE)
    parser.add_argument("--medium-sample-size", type=int, default=DEFAULT_MEDIUM_SAMPLE_SIZE)
    parser.add_argument("--deep-sample-size", type=int, default=DEFAULT_DEEP_SAMPLE_SIZE)
    parser.add_argument("--interview-engine", choices=sorted(ALLOWED_INTERVIEW_ENGINES), default="llm_short_all")
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--stop-after", choices=STOP_AFTER_CHOICES)
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
    if not args.margins and not args.margins_json:
        raise SystemExit("one of --margins or --margins-json is required")
    if not args.dimension and not args.dimension_json:
        raise SystemExit("at least one of --dimension or --dimension-json is required")
    result = run_country_scenario(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"passed", "config_created", "awaiting_llm_responses", "stopped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
