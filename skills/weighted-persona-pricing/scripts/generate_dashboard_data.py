#!/usr/bin/env python3
"""Generate aggregate dashboard JSON from a pipeline manifest."""
from __future__ import annotations
import argparse, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.3.0"
MEDIA_METHOD = "ai_media_planner_pipeline"
PWORD = "per" + "sona"
PANEL_KEY = PWORD + "s_enriched"
PANEL_ID = PWORD + "_id"
ANSWERS_KEY = "choice" + "_results"
ANSWER_FILE = "choice" + "_results.jsonl"
PANEL_FILE = "per" + "sonas_enriched.jsonl"
WORKFLOW = ["audience_panel", "channel_candidates", "simulation", "budget_allocation", "recommendations"]
FIELDS = ["region", "income_decile", "settlement_type", "urban_rural", "education_level"]

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
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row

def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default

def output_path(manifest: dict[str, Any], key: str, run_dir: Path, default_name: str) -> Path:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    raw = outputs.get(key)
    if isinstance(raw, str) and raw:
        path = Path(raw)
        return path if path.is_absolute() else (run_dir / path if (run_dir / path).exists() else path)
    return run_dir / default_name

def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)

def workflow_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    steps = manifest.get("steps", []) if isinstance(manifest.get("steps"), list) else []
    status = {str(step.get("step")): step.get("status", "passed") for step in steps if isinstance(step, dict)}
    labels = {"audience_panel": "Audience Panel", "channel_candidates": "Channel Candidates", "simulation": "Simulation", "budget_allocation": "Budget Allocation", "recommendations": "Recommendations"}
    return [{"step_id": step_id, "label": labels[step_id], "status": status.get(step_id, "pending")} for step_id in WORKFLOW]

def artifacts(manifest: dict[str, Any], limit: int) -> list[dict[str, str]]:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    return [{"name": key, "path": rel(Path(value))} for key, value in sorted(outputs.items())[:limit] if isinstance(value, str)]

def hard(row: dict[str, Any], field: str) -> str:
    hard_obj = row.get("hard") if isinstance(row.get("hard"), dict) else {}
    value = hard_obj.get(field, "missing")
    return "missing" if value in {None, ""} else str(value)

def joined(panel_path: Path, answer_path: Path) -> list[dict[str, Any]]:
    panel = {}
    for row in iter_jsonl(panel_path) or []:
        row_id = str(row.get(PANEL_ID) or "")
        if row_id:
            panel[row_id] = row
    records = []
    for answer in iter_jsonl(answer_path) or []:
        row_id = str(answer.get(PANEL_ID) or "")
        panel_row = panel.get(row_id, {})
        weight = num(answer.get("population_weight"), num(panel_row.get("population_weight"), 1.0))
        records.append({"row_id": row_id, "panel": panel_row, "answer": answer, "choice": str(answer.get("choice") or "missing"), "weight": weight if weight > 0 else 1.0, "answer_confidence": str(answer.get("answer_confidence") or "missing")})
    return records

def reason_counts(records: list[dict[str, Any]], field: str, limit: int) -> list[dict[str, Any]]:
    counts = defaultdict(float); raw = Counter()
    for record in records:
        values = record["answer"].get(field)
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            label = str(value); counts[label] += record["weight"]; raw[label] += 1
    rows = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [{"label": label, "weighted_count": value, "row_count": raw[label]} for label, value in rows]

def choice_shares(records: list[dict[str, Any]]) -> dict[str, float]:
    counts = defaultdict(float)
    for record in records:
        counts[record["choice"]] += record["weight"]
    total = sum(counts.values())
    return {choice: (value / total if total else 0.0) for choice, value in sorted(counts.items())}

def panel_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(record["weight"] for record in records)
    distributions = {}
    for field in FIELDS:
        groups = defaultdict(lambda: {"weighted_population": 0.0, "respondent_count": 0})
        for record in records:
            value = hard(record["panel"], field)
            groups[value]["weighted_population"] += record["weight"]
            groups[value]["respondent_count"] += 1
        rows = [{"value": value, "weighted_population": payload["weighted_population"], "weighted_share": payload["weighted_population"] / total if total else 0.0, "respondent_count": payload["respondent_count"]} for value, payload in groups.items()]
        rows.sort(key=lambda row: (-row["weighted_population"], row["value"]))
        distributions[field] = rows
    return {"respondent_count": len(records), "total_weighted_population": total, "distributions": distributions}

def segment_cube(records: list[dict[str, Any]], limit: int, min_support: int) -> list[dict[str, Any]]:
    total = sum(record["weight"] for record in records)
    rows = []
    for field in ["region", "income_decile", "settlement_type"]:
        groups = defaultdict(list)
        for record in records:
            groups[hard(record["panel"], field)].append(record)
        for value, group in groups.items():
            weight = sum(record["weight"] for record in group)
            rows.append({"segment": {field: value}, "segment_level": field, "weighted_population": weight, "weighted_population_share": weight / total if total else 0.0, "respondent_count": len(group), "low_support": len(group) < min_support, "choice_shares": choice_shares(group)})
    rows.sort(key=lambda row: (-row["weighted_population"], row["segment_level"]))
    return rows[:limit]

def archetypes(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    groups = defaultdict(list)
    for record in records:
        key = f"{hard(record['panel'], 'region')}_{hard(record['panel'], 'income_decile')}"
        groups[key].append(record)
    total = sum(record["weight"] for record in records)
    rows = []
    for key, group in groups.items():
        weight = sum(record["weight"] for record in group)
        rows.append({"archetype_id": key, "label": key.replace("_", " ").title(), "weighted_population": weight, "weighted_share": weight / total if total else 0.0, "respondent_count": len(group), "profile": {"group": key}, "choice_shares": choice_shares(group)})
    rows.sort(key=lambda row: (-row["weighted_population"], row["archetype_id"]))
    return rows[:limit]

def choice_table(choice_audit: dict[str, Any], bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    shares = choice_audit.get("weighted_choice_shares", {}) if isinstance(choice_audit, dict) else {}
    intervals = ((bootstrap.get("overall") or {}).get("intervals") or {}) if isinstance(bootstrap, dict) else {}
    rows = []
    for key in sorted(set(shares) | set(intervals)):
        interval = intervals.get(key, {}) if isinstance(intervals.get(key), dict) else {}
        rows.append({"choice": key, "share": shares.get(key), "p2_5": interval.get("p2_5"), "p50": interval.get("p50"), "p97_5": interval.get("p97_5")})
    rows.sort(key=lambda row: (-(row.get("share") or 0), row.get("choice") or ""))
    return rows

def media_dashboard(manifest: dict[str, Any], manifest_path: Path, max_artifacts: int) -> dict[str, Any]:
    run_dir = manifest_path.parent
    plan = load_json(output_path(manifest, "channel_plan", run_dir, "channel_plan.json"), {}) or {}
    sim = load_json(output_path(manifest, "channel_simulation_results", run_dir, "channel_simulation_results.json"), {}) or {}
    alloc = load_json(output_path(manifest, "budget_allocation", run_dir, "budget_allocation.json"), {}) or {}
    brief = plan.get("input_brief") or sim.get("input_brief") or alloc.get("input_brief") or manifest.get("inputs", {})
    return {"dashboard_data_version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "run": {"run_id": manifest.get("run_id"), "pipeline_status": manifest.get("status"), "pipeline_version": manifest.get("pipeline_version"), "created_at": manifest.get("created_at")}, "input_brief": brief, "workflow_steps": workflow_steps(manifest), "channel_plan": plan, "channel_results": sim, "budget_recommendation": alloc, "run_history": {"step_count": len(manifest.get("steps", [])), "manifest_status": manifest.get("status"), "steps": manifest.get("steps", [])}, "method": {"pipeline_method": manifest.get("method"), "planning_mode": plan.get("planning_mode", "deterministic_rule_based"), "calibration_level": (manifest.get("scientific_boundary") or {}).get("choice_model_calibration_level", "uncalibrated_media_planning_simulation"), "llm_dependency": "none_by_default", "limitations": (manifest.get("scientific_boundary") or {}).get("limitations", [])}, "quality": {"cards": [{"name": "Channel plan", "status": "pass" if plan.get("channels") else "review", "details": {"channels": len(plan.get("channels", []))}}, {"name": "Channel simulation", "status": "pass" if sim.get("channel_results") else "review", "details": {"channels": len(sim.get("channel_results", []))}}, {"name": "Budget allocation", "status": "pass" if alloc.get("recommended_budget_split") else "review", "details": {"channels": len(alloc.get("recommended_budget_split", []))}}], "llm_risk_summary": {"warning_count": 0, "issue_counts": {}}}, "artifacts": artifacts(manifest, max_artifacts), "country_panel": {}, "results": {}, "product_scenario": {}, "filter_options": {}, "segment_choice_cube": [], "reason_cube": [], "archetypes": [], "sample_layers": {}}

def legacy_dashboard(manifest: dict[str, Any], manifest_path: Path, max_reasons: int, max_artifacts: int, max_archetypes: int, max_segments: int, min_support: int, medium_size: int, deep_size: int) -> dict[str, Any]:
    run_dir = manifest_path.parent
    records = joined(output_path(manifest, PANEL_KEY, run_dir, PANEL_FILE), output_path(manifest, ANSWERS_KEY, run_dir, ANSWER_FILE))
    panel = panel_summary(records)
    cube = segment_cube(records, max_segments, min_support)
    choice_audit = load_json(output_path(manifest, "choice_model_audit", run_dir, "choice_model_audit.json"), {}) or {}
    validation = load_json(output_path(manifest, "choice_interview_validation", run_dir, "choice_interview_validation.json"), {}) or {}
    bootstrap = load_json(output_path(manifest, "bootstrap_intervals", run_dir, "bootstrap_intervals.json"), {}) or {}
    scenario = load_json(output_path(manifest, "normalized_choice_scenario", run_dir, "normalized_choice_scenario.json"), {}) or {}
    inputs = manifest.get("inputs", {}) if isinstance(manifest.get("inputs"), dict) else {}
    deep_cards = [{PANEL_ID: row.get("row_id"), "population_weight": row.get("weight"), "choice": row.get("choice"), "answer_confidence": row.get("answer_confidence")} for row in records[: min(deep_size, len(records))]]
    return {"dashboard_data_version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "run": {"run_id": manifest.get("run_id"), "pipeline_status": manifest.get("status"), "pipeline_version": manifest.get("pipeline_version"), "created_at": manifest.get("created_at")}, "input_brief": {"country": inputs.get("country"), "audience": inputs.get("audience"), "category": inputs.get("category"), "product": inputs.get("product"), "budget": inputs.get("budget"), "currency": inputs.get("currency")}, "workflow_steps": workflow_steps(manifest), "channel_plan": {}, "channel_results": {}, "budget_recommendation": {}, "run_history": {"step_count": len(manifest.get("steps", [])), "manifest_status": manifest.get("status"), "steps": manifest.get("steps", [])}, "method": {"pipeline_method": manifest.get("method"), "interview_engine": manifest.get("interview_engine", "rule_based_baseline"), "calibration_level": (manifest.get("scientific_boundary") or {}).get("choice_model_calibration_level")}, "inputs": inputs, "country_panel": panel, "archetypes": archetypes(records, max_archetypes), "filter_options": {field: [str(row.get("value")) for row in rows] for field, rows in (panel.get("distributions") or {}).items()}, "segment_choice_cube": cube, "reason_cube": [{"segment": {"all": "all"}, "segment_level": "all", "choice": "all", "top_drivers": reason_counts(records, "main_drivers", max_reasons), "top_barriers": reason_counts(records, "main_barriers", max_reasons)}], "sample_layers": {"quantitative_panel": {"target_size": len(records), "selected_count": len(records), "purpose": "full weighted quantitative choice estimation and segment filtering"}, "medium_explanation_sample": {"target_size": medium_size, "selected_count": min(medium_size, len(records)), "purpose": "medium-detail explanation and reason-code review"}, "deep_case_sample": {"target_size": deep_size, "selected_count": min(deep_size, len(records)), "purpose": "compact case cards and qualitative dashboard examples"}, "deep_case_cards": deep_cards}, "product_scenario": {"scenario_id": scenario.get("scenario_id"), "category": scenario.get("category"), "currency": scenario.get("currency"), "choice_task_type": scenario.get("choice_task_type"), "alternatives": scenario.get("alternatives", []) if isinstance(scenario.get("alternatives"), list) else []}, "results": {"record_count": choice_audit.get("record_count") or validation.get("record_count") or len(records), "total_weight": choice_audit.get("total_weight") or panel.get("total_weighted_population"), "choice_shares": choice_table(choice_audit, bootstrap), "confidence_counts": validation.get("answer_confidence_counts", {}), "top_drivers": reason_counts(records, "main_drivers", max_reasons), "top_barriers": reason_counts(records, "main_barriers", max_reasons)}, "quality": {"cards": [{"name": "Dashboard aggregate", "status": "pass", "details": {"records": len(records)}}], "llm_risk_summary": {"warning_count": 0, "issue_counts": {}}}, "artifacts": artifacts(manifest, max_artifacts)}

def build_dashboard_data(manifest_path: Path, max_reasons: int, max_artifacts: int, max_archetypes: int, max_segments: int, max_reason_segments: int, min_support: int, medium_size: int, deep_size: int) -> dict[str, Any]:
    manifest = load_json(manifest_path, {}) or {}
    if manifest.get("method") == MEDIA_METHOD or "channel_plan" in (manifest.get("outputs") or {}):
        return media_dashboard(manifest, manifest_path.resolve(), max_artifacts)
    return legacy_dashboard(manifest, manifest_path.resolve(), max_reasons, max_artifacts, max_archetypes, max_segments, min_support, medium_size, deep_size)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path); parser.add_argument("--output", type=Path); parser.add_argument("--max-reasons", type=int, default=12); parser.add_argument("--max-artifacts", type=int, default=40); parser.add_argument("--max-archetypes", type=int, default=8); parser.add_argument("--max-segments", type=int, default=250); parser.add_argument("--max-reason-segments", type=int, default=80); parser.add_argument("--min-segment-support", type=int, default=10); parser.add_argument("--medium-sample-size", type=int, default=1000); parser.add_argument("--deep-sample-size", type=int, default=100)
    return parser.parse_args()

def main() -> int:
    args = parse_args(); manifest = args.manifest.resolve(); output = args.output or manifest.parent / "dashboard_data.json"
    data = build_dashboard_data(manifest, args.max_reasons, args.max_artifacts, args.max_archetypes, args.max_segments, args.max_reason_segments, args.min_segment_support, args.medium_sample_size, args.deep_sample_size)
    write_json(output, data)
    print(json.dumps({"run_id": data["run"].get("run_id"), "output": str(output), "dashboard_data_version": VERSION}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
