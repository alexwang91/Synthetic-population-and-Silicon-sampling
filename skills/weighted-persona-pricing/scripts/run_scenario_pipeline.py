#!/usr/bin/env python3
"""Run the AI media-planner scenario pipeline from a minimal brief."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_VERSION = "0.2.0"
MEDIA_METHOD = "ai_media_planner_pipeline"

def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value

def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "run"

def script_path(relative: str) -> Path:
    return repo_root() / relative

def run_command(command: list[str], *, cwd: Path, step_name: str) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    completed = datetime.now(timezone.utc).isoformat()
    result = {"step": step_name, "command": command, "command_text": " ".join(command), "returncode": process.returncode, "started_at": started, "completed_at": completed, "stdout": process.stdout[-4000:], "stderr": process.stderr[-4000:], "status": "passed" if process.returncode == 0 else "failed"}
    if process.returncode != 0:
        raise RuntimeError(f"step {step_name} failed with code {process.returncode}:\n{process.stderr}\n{process.stdout}")
    return result

def internal_step(step_name: str, command_text: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {"step": step_name, "command": [command_text], "command_text": command_text, "returncode": 0, "started_at": now, "completed_at": now, "stdout": "", "stderr": "", "status": "passed"}

def normalize_brief(args: argparse.Namespace) -> dict[str, Any]:
    missing = [name for name in ["country", "audience", "category", "budget"] if getattr(args, name) in {None, ""}]
    if missing:
        raise ValueError(f"minimal media-planner mode requires: {missing}")
    if args.budget <= 0:
        raise ValueError("--budget must be positive")
    return {"country": args.country, "audience": args.audience, "category": args.category, "product": args.product or args.category, "budget": float(args.budget), "currency": args.currency}

def run_id_for(brief: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return slug(explicit)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return slug(f"{brief['country']}_{brief['audience']}_{brief['category']}_{stamp}")

def outputs_for(run_dir: Path) -> dict[str, Path]:
    return {"scenario_brief": run_dir / "scenario_brief.json", "channel_plan": run_dir / "channel_plan.json", "channel_simulation_results": run_dir / "channel_simulation_results.json", "budget_allocation": run_dir / "budget_allocation.json", "dashboard_data": run_dir / "dashboard_data.json", "market_report_md": run_dir / "market_report.md", "market_report_json": run_dir / "market_report.json"}

def manifest_for(run_id: str, run_dir: Path, brief: dict[str, Any], outputs: dict[str, Path], steps: list[dict[str, Any]], status: str) -> dict[str, Any]:
    manifest = {"run_id": run_id, "status": status, "pipeline_version": PIPELINE_VERSION, "created_at": steps[0]["started_at"] if steps else datetime.now(timezone.utc).isoformat(), "method": MEDIA_METHOD, "interview_engine": "deterministic_media_planner", "inputs": brief, "outputs": {key: str(path) for key, path in outputs.items()}, "steps": steps, "scientific_boundary": {"pipeline_changes_model_outputs": False, "choice_model_calibration_level": "uncalibrated_media_planning_simulation", "original_plan_alignment": "minimal brief to deterministic channel plan, offline channel simulation, budget allocation, and dashboard", "report_policy": "short decision memo; dashboard is the primary decision surface", "token_policy": "offline default; no LLM calls required", "acceptance_policy": "all aggregate artifacts must be written into the run folder", "llm_risk_controls": ["none_by_default"], "limitations": ["ROI, ROAS, CAC, reach, and conversions are synthetic planning estimates, not observed campaign data."]}}
    write_json(run_dir / "manifest.json", manifest)
    return manifest

def write_report(run_dir: Path, brief: dict[str, Any], simulation: dict[str, Any], allocation: dict[str, Any], outputs: dict[str, Path]) -> None:
    split = allocation.get("recommended_budget_split", [])
    summary = allocation.get("summary", {})
    lines = [f"# Media Planner Report: {brief['country']} / {brief['audience']} / {brief['category']}", "", "## Executive Summary", f"- Budget: {brief['budget']:.0f} {brief.get('currency','EUR')}", f"- Best channel: {summary.get('best_channel', 'n/a')}", f"- Highest scale channel: {summary.get('highest_scale_channel', 'n/a')}", f"- Holdout budget: {summary.get('holdout_budget', 0)} {summary.get('currency', brief.get('currency','EUR'))}", "", "## Recommended Budget Split"]
    for row in split:
        lines.append(f"- P{row.get('priority')}: {row.get('name') or row.get('channel_id')} — {row.get('budget')} {summary.get('currency', brief.get('currency','EUR'))}, ROI {row.get('expected_roi')}, CAC {row.get('expected_cac')}, risk {row.get('risk')}. {row.get('execution_advice')}")
    lines.extend(["", "## Method Boundary", "Deterministic offline media-planning simulation. Use real platform data, holdouts, and experiments before treating estimates as decision-grade truth."])
    outputs["market_report_md"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(outputs["market_report_json"], {"input_brief": brief, "summary": summary, "recommended_budget_split": split, "channel_results": simulation.get("channel_results", []), "limitations": simulation.get("limitations", [])})

def media_pipeline(brief: dict[str, Any], output_root: Path, run_id: str, risk_preference: str) -> dict[str, Any]:
    root = repo_root()
    run_dir = (output_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    outputs = outputs_for(run_dir)
    write_json(outputs["scenario_brief"], brief)
    steps = [internal_step("audience_panel", "write minimal input brief")]
    manifest_for(run_id, run_dir, brief, outputs, steps, "running")
    py = sys.executable
    commands = [
        ("channel_candidates", [py, str(script_path("skills/weighted-persona-pricing/scripts/generate_channel_plan.py")), str(outputs["scenario_brief"]), "--output", str(outputs["channel_plan"])]),
        ("simulation", [py, str(script_path("skills/weighted-persona-pricing/scripts/run_channel_simulation.py")), str(outputs["channel_plan"]), "--budget", str(brief["budget"]), "--output", str(outputs["channel_simulation_results"])]),
        ("budget_allocation", [py, str(script_path("skills/weighted-persona-pricing/scripts/generate_budget_allocation.py")), str(outputs["channel_simulation_results"]), "--budget", str(brief["budget"]), "--risk-preference", risk_preference, "--output", str(outputs["budget_allocation"])]),
    ]
    for name, command in commands:
        steps.append(run_command(command, cwd=root, step_name=name))
        manifest_for(run_id, run_dir, brief, outputs, steps, "running")
    simulation = load_json(outputs["channel_simulation_results"])
    allocation = load_json(outputs["budget_allocation"])
    write_report(run_dir, brief, simulation, allocation, outputs)
    steps.append(internal_step("recommendations", "write report and recommendations"))
    manifest_for(run_id, run_dir, brief, outputs, steps, "running")
    steps.append(run_command([py, str(script_path("skills/weighted-persona-pricing/scripts/generate_dashboard_data.py")), str(run_dir / "manifest.json"), "--output", str(outputs["dashboard_data"])], cwd=root, step_name="generate_dashboard_data"))
    return manifest_for(run_id, run_dir, brief, outputs, steps, "passed")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path, help="Legacy config mode is not used by the media-planner CLI path.")
    parser.add_argument("--output-root", type=Path, default=Path("runs"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--country")
    parser.add_argument("--audience")
    parser.add_argument("--category")
    parser.add_argument("--product")
    parser.add_argument("--budget", type=float)
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--risk-preference", choices=["conservative", "balanced", "aggressive"], default="balanced")
    parser.add_argument("--run-id")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    if args.config and not args.country:
        raise ValueError("This entry point now expects the minimal media-planner flags: --country --audience --category --budget")
    brief = normalize_brief(args)
    run_id = run_id_for(brief, args.run_id)
    manifest = media_pipeline(brief, args.output_root, run_id, args.risk_preference)
    if args.manifest:
        write_json(args.manifest, manifest)
    print(json.dumps({"run_id": manifest["run_id"], "status": manifest["status"], "manifest": str(Path(args.output_root) / manifest["run_id"] / "manifest.json")}, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
