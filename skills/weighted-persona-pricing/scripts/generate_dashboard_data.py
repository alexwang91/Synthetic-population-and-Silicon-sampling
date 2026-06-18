#!/usr/bin/env python3
"""Generate dashboard-ready JSON from a scenario pipeline manifest.

This script is a presentation-data layer. It does not create or modify choices.
It consolidates aggregate results, uncertainty intervals, method settings,
quality diagnostics, subgroup diagnostics, and artifact links into one JSON file
for a future HTML/dashboard UI.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DASHBOARD_DATA_VERSION = "0.1.0"


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                value["_line_number"] = line_number
                yield value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_output(manifest: dict[str, Any], key: str, run_dir: Path, default_name: str) -> Path:
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    raw = outputs.get(key)
    if isinstance(raw, str) and raw:
        return Path(raw)
    return run_dir / default_name


def rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


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


def weighted_reason_counts(choice_results: Path, field: str, max_items: int) -> list[dict[str, Any]]:
    counts: dict[str, float] = defaultdict(float)
    raw_counts: Counter[str] = Counter()
    for row in iter_jsonl(choice_results) or []:
        weight = numeric(row.get("population_weight"), 1.0)
        if weight <= 0:
            weight = 1.0
        values = row.get(field)
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            label = str(value)
            counts[label] += weight
            raw_counts[label] += 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_items]
    return [{"label": label, "weighted_count": value, "row_count": raw_counts[label]} for label, value in ordered]


def choice_rows(choice_audit: dict[str, Any], bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    shares = choice_audit.get("weighted_choice_shares", {}) if isinstance(choice_audit, dict) else {}
    if not isinstance(shares, dict):
        shares = {}
    intervals = {}
    point = {}
    if isinstance(bootstrap, dict):
        overall = bootstrap.get("overall", {}) if isinstance(bootstrap.get("overall"), dict) else {}
        intervals = overall.get("intervals", {}) if isinstance(overall.get("intervals"), dict) else {}
        point = overall.get("point", {}) if isinstance(overall.get("point"), dict) else {}
    if not shares:
        shares = point
    keys = sorted(set(shares) | set(intervals))
    rows = []
    for key in keys:
        interval = intervals.get(key, {}) if isinstance(intervals.get(key), dict) else {}
        rows.append(
            {
                "choice": key,
                "share": shares.get(key),
                "p2_5": interval.get("p2_5"),
                "p50": interval.get("p50"),
                "p97_5": interval.get("p97_5"),
            }
        )
    rows.sort(key=lambda row: (-(row.get("share") or 0), row.get("choice") or ""))
    return rows


def audit_card(name: str, status: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": status, "details": details}


def build_quality_cards(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    ipf = artifacts.get("ipf_audit") or {}
    cards.append(audit_card("IPF / raking", "pass" if ipf.get("converged") is True else "review", {"iterations": ipf.get("iterations_completed"), "warnings": ipf.get("warning_count")}))
    persona = artifacts.get("persona_coherence_audit") or {}
    cards.append(audit_card("Persona coherence", "pass" if persona.get("passes_persona_coherence") is True else "review", {"errors": persona.get("error_count"), "warnings": persona.get("warning_count")}))
    product = artifacts.get("product_scenario_audit") or {}
    cards.append(audit_card("Product scenario", "pass" if product.get("passes_product_scenario_normalization") is True else "review", {"alternatives": product.get("alternative_count"), "outside_option": product.get("outside_option_included")}))
    choice = artifacts.get("choice_interview_validation") or {}
    cards.append(audit_card("Choice row integrity", "pass" if choice.get("passes_choice_interview_integrity") is True else "review", {"records": choice.get("record_count"), "errors": choice.get("error_count"), "warnings": choice.get("warning_count")}))
    llm_quality = artifacts.get("llm_choice_quality_audit") or {}
    if llm_quality:
        cards.append(
            audit_card(
                "LLM choice quality",
                "pass" if llm_quality.get("passes_llm_choice_quality_validation") is True else "review",
                {"errors": llm_quality.get("error_count"), "warnings": llm_quality.get("warning_count")},
            )
        )
    artifact_validation = artifacts.get("pipeline_artifact_validation") or {}
    if artifact_validation:
        cards.append(
            audit_card(
                "Pipeline artifact validation",
                "pass" if artifact_validation.get("passes_pipeline_artifact_validation") is True else "review",
                {"errors": artifact_validation.get("error_count"), "warnings": artifact_validation.get("warning_count")},
            )
        )
    return cards


def product_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    alternatives = []
    for item in scenario.get("alternatives", []) if isinstance(scenario.get("alternatives"), list) else []:
        if not isinstance(item, dict):
            continue
        alternatives.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "is_outside_option": item.get("is_outside_option"),
                "price": item.get("price"),
                "currency": item.get("currency", scenario.get("currency")),
                "normalized_attributes": item.get("normalized_attributes", {}),
            }
        )
    return {
        "scenario_id": scenario.get("scenario_id"),
        "category": scenario.get("category"),
        "currency": scenario.get("currency"),
        "choice_task_type": scenario.get("choice_task_type"),
        "alternatives": alternatives,
    }


def risk_summary(llm_quality: dict[str, Any]) -> dict[str, Any]:
    warnings = llm_quality.get("warnings", []) if isinstance(llm_quality.get("warnings"), list) else []
    errors = llm_quality.get("errors", []) if isinstance(llm_quality.get("errors"), list) else []
    issue_counts: Counter[str] = Counter()
    for item in warnings + errors:
        if isinstance(item, dict):
            issue_counts[str(item.get("issue", "unknown"))] += 1
    return {
        "error_count": llm_quality.get("error_count", 0),
        "warning_count": llm_quality.get("warning_count", 0),
        "issue_counts": dict(issue_counts),
        "warnings": warnings[:20],
        "errors": errors[:20],
        "choice_distribution": llm_quality.get("choice_distribution", {}),
        "confidence_distribution": llm_quality.get("confidence_distribution", {}),
        "subgroup_choice_analysis": (llm_quality.get("diagnostics", {}) or {}).get("subgroup_choice_analysis", {}),
        "position_shares": (llm_quality.get("diagnostics", {}) or {}).get("position_shares", {}),
    }


def build_dashboard_data(manifest_path: Path, max_reasons: int, max_artifacts: int) -> dict[str, Any]:
    manifest = load_json(manifest_path, {}) or {}
    run_dir = manifest_path.resolve().parent
    root = Path.cwd()
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    boundary = manifest.get("scientific_boundary", {}) if isinstance(manifest.get("scientific_boundary"), dict) else {}
    inputs = manifest.get("inputs", {}) if isinstance(manifest.get("inputs"), dict) else {}

    paths = {
        "choice_results": resolve_output(manifest, "choice_results", run_dir, "choice_results.jsonl"),
        "choice_model_audit": resolve_output(manifest, "choice_model_audit", run_dir, "choice_model_audit.json"),
        "llm_choice_prompt_audit": resolve_output(manifest, "llm_choice_prompt_audit", run_dir, "llm_choice_prompt_audit.json"),
        "llm_choice_interview_audit": resolve_output(manifest, "llm_choice_interview_audit", run_dir, "llm_choice_interview_audit.json"),
        "llm_choice_quality_audit": resolve_output(manifest, "llm_choice_quality_audit", run_dir, "llm_choice_quality_audit.json"),
        "choice_interview_validation": resolve_output(manifest, "choice_interview_validation", run_dir, "choice_interview_validation.json"),
        "bootstrap_intervals": resolve_output(manifest, "bootstrap_intervals", run_dir, "bootstrap_intervals.json"),
        "persona_coherence_audit": resolve_output(manifest, "persona_coherence_audit", run_dir, "persona_coherence_audit.json"),
        "ipf_audit": resolve_output(manifest, "ipf_audit", run_dir, "ipf_audit.json"),
        "product_scenario_audit": resolve_output(manifest, "product_scenario_audit", run_dir, "product_scenario_audit.json"),
        "normalized_choice_scenario": resolve_output(manifest, "normalized_choice_scenario", run_dir, "normalized_choice_scenario.json"),
        "pipeline_artifact_validation": resolve_output(manifest, "pipeline_artifact_validation", run_dir, "pipeline_artifact_validation.json"),
        "market_report_json": resolve_output(manifest, "market_report_json", run_dir, "market_report.json"),
    }

    artifacts = {key: load_json(path, {}) or {} for key, path in paths.items() if key != "choice_results"}
    choice_model = artifacts.get("choice_model_audit") or {}
    bootstrap = artifacts.get("bootstrap_intervals") or {}
    validation = artifacts.get("choice_interview_validation") or {}
    llm_quality = artifacts.get("llm_choice_quality_audit") or {}
    llm_prompt = artifacts.get("llm_choice_prompt_audit") or {}
    llm_interview = artifacts.get("llm_choice_interview_audit") or {}

    artifact_list = []
    for key, raw in sorted(outputs.items()):
        if len(artifact_list) >= max_artifacts:
            break
        if isinstance(raw, str):
            artifact_list.append({"name": key, "path": rel(Path(raw), root)})

    total_weight = choice_model.get("total_weight") or bootstrap.get("total_weight")
    if not total_weight and isinstance(bootstrap.get("overall"), dict):
        total_weight = bootstrap.get("overall", {}).get("total_weight")

    return {
        "dashboard_data_version": DASHBOARD_DATA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run": {
            "run_id": manifest.get("run_id"),
            "pipeline_status": manifest.get("status"),
            "pipeline_version": manifest.get("pipeline_version"),
            "created_at": manifest.get("created_at"),
        },
        "method": {
            "pipeline_method": manifest.get("method"),
            "interview_engine": manifest.get("interview_engine", "rule_based_baseline"),
            "calibration_level": boundary.get("choice_model_calibration_level"),
            "order_policy": inputs.get("llm_order_policy") or llm_prompt.get("order_policy"),
            "prompt_variant": inputs.get("llm_prompt_variant") or llm_prompt.get("prompt_variant"),
            "prompt_version": llm_prompt.get("prompt_version") or llm_interview.get("prompt_version"),
            "original_plan_alignment": boundary.get("original_plan_alignment"),
            "llm_risk_controls": boundary.get("llm_risk_controls", []),
            "limitations": boundary.get("limitations", []),
        },
        "inputs": inputs,
        "product_scenario": product_summary(artifacts.get("normalized_choice_scenario") or {}),
        "results": {
            "record_count": choice_model.get("record_count") or validation.get("record_count"),
            "total_weight": total_weight,
            "choice_shares": choice_rows(choice_model, bootstrap),
            "confidence_counts": validation.get("answer_confidence_counts", {}),
            "top_drivers": weighted_reason_counts(paths["choice_results"], "main_drivers", max_reasons),
            "top_barriers": weighted_reason_counts(paths["choice_results"], "main_barriers", max_reasons),
        },
        "quality": {
            "cards": build_quality_cards(artifacts),
            "llm_risk_summary": risk_summary(llm_quality),
            "choice_validation": validation,
            "pipeline_artifact_validation": artifacts.get("pipeline_artifact_validation") or {},
        },
        "artifacts": artifact_list,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-reasons", type=int, default=12)
    parser.add_argument("--max-artifacts", type=int, default=40)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_reasons <= 0:
        raise ValueError("--max-reasons must be positive")
    if args.max_artifacts <= 0:
        raise ValueError("--max-artifacts must be positive")
    manifest = args.manifest.resolve()
    output = args.output or manifest.parent / "dashboard_data.json"
    data = build_dashboard_data(manifest, args.max_reasons, args.max_artifacts)
    write_json(output, data)
    print(json.dumps({"run_id": data["run"].get("run_id"), "output": str(output), "dashboard_data_version": DASHBOARD_DATA_VERSION}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
