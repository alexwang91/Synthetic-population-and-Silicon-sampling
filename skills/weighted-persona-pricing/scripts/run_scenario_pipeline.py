#!/usr/bin/env python3
"""Run the synthetic market-research scenario pipeline.

This orchestrator wires existing audited steps together. It does not alter
statistical weights, soft traits, product normalization, or choice logic.

The pipeline supports two choice-generation engines:

- rule_based_baseline: deterministic development baseline and CI smoke path.
- llm_short_all: intended synthetic respondent mode; exports one isolated short
  interview prompt per selected representative persona, then optionally
  normalizes external LLM batch responses into choice_results.jsonl.

The pipeline writes every intermediate artifact into a run directory and
records a manifest with command, input, output, and status metadata for each
step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PIPELINE_VERSION = "0.1.0"
ALLOWED_INTERVIEW_ENGINES = {"rule_based_baseline", "llm_short_all"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def resolve_path(path_value: str | Path, *, base_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    candidate = base_dir / path
    if candidate.exists():
        return candidate.resolve()
    return (repo_root() / path).resolve()


def maybe_resolve_path(path_value: str | Path | None, *, base_dir: Path) -> Path | None:
    if path_value is None:
        return None
    return resolve_path(path_value, base_dir=base_dir)


def script_path(relative: str) -> Path:
    return repo_root() / relative


def command_as_text(command: list[str]) -> str:
    return " ".join(command)


def run_command(command: list[str], *, cwd: Path, step_name: str, allow_failure: bool = False) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    completed = datetime.now(timezone.utc).isoformat()
    result = {
        "step": step_name,
        "command": command,
        "command_text": command_as_text(command),
        "returncode": process.returncode,
        "started_at": started,
        "completed_at": completed,
        "stdout": process.stdout[-4000:],
        "stderr": process.stderr[-4000:],
        "status": "passed" if process.returncode == 0 else "failed",
    }
    if process.returncode != 0 and not allow_failure:
        raise RuntimeError(f"step {step_name} failed with code {process.returncode}:\n{process.stderr}\n{process.stdout}")
    return result


def write_dimension_json(dimensions: dict[str, Any], path: Path) -> None:
    if not isinstance(dimensions, dict) or not dimensions:
        raise ValueError("config.dimensions must be a non-empty object")
    normalized: dict[str, list[str]] = {}
    for key, values in dimensions.items():
        if not isinstance(key, str) or not key:
            raise ValueError("dimension names must be non-empty strings")
        if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values):
            raise ValueError(f"dimension {key!r} must be a non-empty string array")
        normalized[key] = values
    write_json(path, normalized)


def build_margin_file(config: dict[str, Any], run_dir: Path, base_dir: Path) -> Path:
    if "margins" in config:
        margin_source = resolve_path(config["margins"], base_dir=base_dir)
        if not margin_source.exists():
            raise FileNotFoundError(f"margins file does not exist: {margin_source}")
        margin_target = run_dir / "margins.json"
        margin_target.write_text(margin_source.read_text(encoding="utf-8-sig"), encoding="utf-8")
        return margin_target
    margins_inline = config.get("margins_inline")
    if isinstance(margins_inline, dict):
        margin_target = run_dir / "margins.json"
        write_json(margin_target, margins_inline)
        return margin_target
    raise ValueError("config must include either 'margins' or 'margins_inline'")


def validate_config(config: dict[str, Any]) -> None:
    required = ["run_id", "country_pack", "dimensions", "sample_size", "product_scenario", "category", "category_price_index"]
    missing = [field for field in required if field not in config]
    if missing:
        raise ValueError(f"missing config fields: {missing}")
    if not isinstance(config["run_id"], str) or not config["run_id"]:
        raise ValueError("run_id must be a non-empty string")
    if not isinstance(config["sample_size"], int) or config["sample_size"] <= 0:
        raise ValueError("sample_size must be a positive integer")
    if not isinstance(config["category"], str) or not config["category"]:
        raise ValueError("category must be a non-empty string")
    price_index = config["category_price_index"]
    if not isinstance(price_index, (int, float)) or not 0 <= float(price_index) <= 1:
        raise ValueError("category_price_index must be a number in [0,1]")
    engine = config.get("interview_engine", "rule_based_baseline")
    if engine not in ALLOWED_INTERVIEW_ENGINES:
        raise ValueError(f"interview_engine must be one of {sorted(ALLOWED_INTERVIEW_ENGINES)}")


def pipeline(config: dict[str, Any], *, config_path: Path, output_root: Path, stop_after: str | None) -> dict[str, Any]:
    validate_config(config)
    root = repo_root()
    config_base = config_path.parent.resolve()
    run_dir = (output_root / config["run_id"]).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    country_pack = resolve_path(config["country_pack"], base_dir=config_base)
    product_scenario = resolve_path(config["product_scenario"], base_dir=config_base)
    llm_response_file = maybe_resolve_path(config.get("llm_response_file"), base_dir=config_base)
    if not country_pack.exists():
        raise FileNotFoundError(f"country pack does not exist: {country_pack}")
    if not product_scenario.exists():
        raise FileNotFoundError(f"product scenario does not exist: {product_scenario}")
    if llm_response_file is not None and not llm_response_file.exists():
        raise FileNotFoundError(f"llm_response_file does not exist: {llm_response_file}")

    dimension_json = run_dir / "dimensions.json"
    write_dimension_json(config["dimensions"], dimension_json)
    margins = build_margin_file(config, run_dir, config_base)
    interview_engine = str(config.get("interview_engine", "rule_based_baseline"))

    outputs = {
        "seed_cells": run_dir / "seed_cells.jsonl",
        "cell_constraints": run_dir / "cell_constraints.json",
        "weighted_cells": run_dir / "weighted_cells.jsonl",
        "ipf_audit": run_dir / "ipf_audit.json",
        "personas_core": run_dir / "personas_core.jsonl",
        "persona_sampling_audit": run_dir / "persona_sampling_audit.json",
        "personas_enriched": run_dir / "personas_enriched.jsonl",
        "soft_trait_audit": run_dir / "soft_trait_audit.json",
        "persona_coherence_audit": run_dir / "persona_coherence_audit.json",
        "normalized_choice_scenario": run_dir / "normalized_choice_scenario.json",
        "product_scenario_audit": run_dir / "product_scenario_audit.json",
        "choice_results": run_dir / "choice_results.jsonl",
        "choice_model_audit": run_dir / "choice_model_audit.json",
        "llm_choice_prompts": run_dir / "llm_choice_prompts.jsonl",
        "llm_choice_prompt_audit": run_dir / "llm_choice_prompt_audit.json",
        "llm_choice_interview_audit": run_dir / "llm_choice_interview_audit.json",
        "choice_interview_validation": run_dir / "choice_interview_validation.json",
        "bootstrap_intervals": run_dir / "bootstrap_intervals.json",
        "market_report_md": run_dir / "market_report.md",
        "market_report_json": run_dir / "market_report.json",
        "pipeline_artifact_validation": run_dir / "pipeline_artifact_validation.json",
    }

    steps: list[dict[str, Any]] = []

    def should_stop(step: str) -> bool:
        return stop_after == step

    def add_step(name: str, command: list[str]) -> bool:
        result = run_command(command, cwd=root, step_name=name)
        steps.append(result)
        return should_stop(name)

    py = sys.executable
    if add_step("validate_country_pack", [py, str(script_path("skills/country-pack-builder/scripts/validate_country_pack.py")), str(country_pack), "--audit", str(run_dir / "country_pack_validation.json")]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    if add_step("country_pack_to_cells", [py, str(script_path("skills/country-pack-builder/scripts/country_pack_to_cells.py")), str(country_pack), "--dimension-json", str(dimension_json), "--output", str(outputs["seed_cells"]), "--constraints-output", str(outputs["cell_constraints"])]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    if add_step("run_ipf", [py, str(script_path("skills/country-pack-builder/scripts/run_ipf.py")), str(outputs["seed_cells"]), str(margins), "--output", str(outputs["weighted_cells"]), "--audit", str(outputs["ipf_audit"]), "--iterations", str(config.get("ipf_iterations", 200)), "--tolerance", str(config.get("ipf_tolerance", 1e-6))]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    if add_step("sample_persona_skeletons", [py, str(script_path("skills/country-pack-builder/scripts/sample_persona_skeletons.py")), str(outputs["weighted_cells"]), "--sample-size", str(config["sample_size"]), "--output", str(outputs["personas_core"]), "--audit", str(outputs["persona_sampling_audit"])]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    if add_step("expand_soft_traits", [py, str(script_path("skills/weighted-persona-pricing/scripts/expand_soft_traits.py")), str(outputs["personas_core"]), "--category", config["category"], "--category-price-index", str(config["category_price_index"]), "--output", str(outputs["personas_enriched"]), "--audit", str(outputs["soft_trait_audit"])]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    if add_step("validate_persona_coherence", [py, str(script_path("skills/weighted-persona-pricing/scripts/validate_persona_coherence.py")), str(outputs["personas_enriched"]), "--audit", str(outputs["persona_coherence_audit"])]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    if add_step("product_scenario_normalizer", [py, str(script_path("skills/weighted-persona-pricing/scripts/product_scenario_normalizer.py")), str(product_scenario), "--output", str(outputs["normalized_choice_scenario"]), "--audit", str(outputs["product_scenario_audit"])]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")

    if interview_engine == "rule_based_baseline":
        if add_step("run_choice_model", [py, str(script_path("skills/weighted-persona-pricing/scripts/run_choice_model.py")), str(outputs["personas_enriched"]), str(outputs["normalized_choice_scenario"]), "--output", str(outputs["choice_results"]), "--audit", str(outputs["choice_model_audit"]), "--mode", str(config.get("choice_mode", "argmax")), "--temperature", str(config.get("choice_temperature", 0.35))]):
            return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    elif interview_engine == "llm_short_all":
        export_command = [
            py,
            str(script_path("skills/weighted-persona-pricing/scripts/run_llm_choice_interviews.py")),
            "export-prompts",
            str(outputs["personas_enriched"]),
            str(outputs["normalized_choice_scenario"]),
            "--output-prompts",
            str(outputs["llm_choice_prompts"]),
            "--audit",
            str(outputs["llm_choice_prompt_audit"]),
        ]
        if config.get("llm_prompt_limit"):
            export_command.extend(["--limit", str(config["llm_prompt_limit"])])
        if config.get("include_story_in_llm_prompt", False):
            export_command.append("--include-story")
            export_command.extend(["--max-story-chars", str(config.get("max_story_chars", 900))])
        if add_step("export_llm_choice_prompts", export_command):
            return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
        if llm_response_file is None:
            return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="awaiting_llm_responses")
        if add_step("normalize_llm_choice_responses", [py, str(script_path("skills/weighted-persona-pricing/scripts/run_llm_choice_interviews.py")), "normalize-responses", str(outputs["llm_choice_prompts"]), str(llm_response_file), "--output", str(outputs["choice_results"]), "--audit", str(outputs["llm_choice_interview_audit"])]):
            return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
    else:
        raise ValueError(f"unsupported interview_engine: {interview_engine}")

    if add_step("validate_choice_interviews", [py, str(script_path("skills/weighted-persona-pricing/scripts/validate_choice_interviews.py")), str(outputs["choice_results"]), "--audit", str(outputs["choice_interview_validation"]), "--require-controls"]):
        return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")

    bootstrap_iterations = int(config.get("bootstrap_iterations", 120))
    if bootstrap_iterations > 0:
        if add_step("bootstrap_choice_intervals", [py, str(script_path("skills/weighted-persona-pricing/scripts/bootstrap_choice_intervals.py")), str(outputs["choice_results"]), "--output", str(outputs["bootstrap_intervals"]), "--iterations", str(bootstrap_iterations), "--seed", str(config.get("bootstrap_seed", 20260618))]):
            return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")

    manifest = finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="passed")
    if config.get("generate_report", True):
        if add_step("generate_market_report", [py, str(script_path("skills/weighted-persona-pricing/scripts/generate_market_report.py")), str(run_dir / "manifest.json"), "--output-md", str(outputs["market_report_md"]), "--output-json", str(outputs["market_report_json"]), "--max-reasons", str(config.get("report_max_reasons", 5)), "--max-artifacts", str(config.get("report_max_artifacts", 18))]):
            return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
        manifest = finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="passed")

    if config.get("validate_artifacts", True):
        if add_step("validate_pipeline_artifacts", [py, str(script_path("skills/weighted-persona-pricing/scripts/validate_pipeline_artifacts.py")), str(run_dir / "manifest.json"), "--audit", str(outputs["pipeline_artifact_validation"]), "--max-report-lines", str(config.get("max_report_lines", 0))]):
            return finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="stopped")
        manifest = finalize_manifest(config, run_dir, country_pack, product_scenario, dimension_json, margins, outputs, steps, status="passed")
    return manifest


def finalize_manifest(
    config: dict[str, Any],
    run_dir: Path,
    country_pack: Path,
    product_scenario: Path,
    dimension_json: Path,
    margins: Path,
    outputs: dict[str, Path],
    steps: list[dict[str, Any]],
    *,
    status: str,
) -> dict[str, Any]:
    interview_engine = str(config.get("interview_engine", "rule_based_baseline"))
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "status": status,
        "run_id": config["run_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "synthetic_respondent_scenario_pipeline",
        "interview_engine": interview_engine,
        "inputs": {
            "country_pack": str(country_pack),
            "product_scenario": str(product_scenario),
            "dimensions": str(dimension_json),
            "margins": str(margins),
            "sample_size": config["sample_size"],
            "category": config["category"],
            "category_price_index": config["category_price_index"],
            "llm_response_file": config.get("llm_response_file"),
        },
        "outputs": {key: str(value) for key, value in outputs.items() if value.exists()},
        "steps": steps,
        "scientific_boundary": {
            "pipeline_changes_model_outputs": False,
            "choice_model_calibration_level": "uncalibrated_rule_based_baseline" if interview_engine == "rule_based_baseline" else "synthetic_llm_respondent_uncalibrated",
            "provenance_policy": "all major intermediate artifacts and audit files are retained",
            "report_policy": "market_report.md is an optional summary surface; complete dashboard data stays in JSON/JSONL artifacts",
            "token_policy": "llm_short_all may ask every selected representative persona one short isolated choice prompt; never summarize all raw row-level interviews in one LLM prompt",
            "acceptance_policy": "pipeline_artifact_validation.json checks required artifacts, critical audit pass flags, and optional report-length warnings",
            "original_plan_alignment": "representative weighted respondents each produce a discrete choice; rule_based_baseline is only an auxiliary baseline, while llm_short_all is the intended synthetic respondent mode",
            "limitations": [
                "Country pack quality and margin validity determine the statistical credibility of generated personas.",
                "Rule-based choices are for development, CI, and comparison; they are not the intended final synthetic respondent simulator.",
                "LLM short-choice rows are synthetic respondent outputs, not observed consumer behavior.",
                "Decision-grade accuracy requires calibration against CBC, survey, sales, clickstream, or experiment data.",
            ],
        },
    }
    write_json(run_dir / "manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("runs"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--stop-after", choices=[
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
        "bootstrap_choice_intervals",
        "generate_market_report",
        "validate_pipeline_artifacts",
    ])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()
    config = load_json(config_path)
    manifest = pipeline(config, config_path=config_path, output_root=args.output_root, stop_after=args.stop_after)
    if args.manifest:
        write_json(args.manifest, manifest)
    print(json.dumps({"run_id": manifest["run_id"], "status": manifest["status"], "manifest": str(Path(args.output_root) / manifest["run_id"] / "manifest.json")}, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] in {"passed", "stopped", "awaiting_llm_responses"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
