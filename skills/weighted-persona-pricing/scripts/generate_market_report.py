#!/usr/bin/env python3
"""Generate a concise market report from a scenario pipeline manifest.

The report is intentionally compact. It summarizes existing audit artifacts and
aggregate choice results without copying persona rows, choice rows, or large
intermediate files into the Markdown body.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPORT_VERSION = "0.1.0"


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * value:.1f}%"


def number(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.3f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value) if value is not None else "n/a"


def artifact_path(manifest: dict[str, Any], key: str, run_dir: Path) -> Path:
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    raw = outputs.get(key)
    if isinstance(raw, str) and raw:
        return Path(raw)
    defaults = {
        "choice_results": "choice_results.jsonl",
        "choice_model_audit": "choice_model_audit.json",
        "choice_interview_validation": "choice_interview_validation.json",
        "bootstrap_intervals": "bootstrap_intervals.json",
        "persona_coherence_audit": "persona_coherence_audit.json",
        "ipf_audit": "ipf_audit.json",
        "product_scenario_audit": "product_scenario_audit.json",
        "soft_trait_audit": "soft_trait_audit.json",
        "persona_sampling_audit": "persona_sampling_audit.json",
        "normalized_choice_scenario": "normalized_choice_scenario.json",
    }
    return run_dir / defaults[key]


def weighted_reason_counts(choice_results: Path, field: str, max_items: int) -> list[dict[str, Any]]:
    counts: dict[str, float] = defaultdict(float)
    raw_counts: Counter[str] = Counter()
    for row in iter_jsonl(choice_results) or []:
        weight = row.get("population_weight", 1.0)
        if not isinstance(weight, (int, float)) or weight <= 0:
            weight = 1.0
        values = row.get(field)
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            label = str(value)
            counts[label] += float(weight)
            raw_counts[label] += 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_items]
    return [{"label": label, "weighted_count": value, "row_count": raw_counts[label]} for label, value in ordered]


def share_rows(choice_audit: dict[str, Any], bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    shares = choice_audit.get("weighted_choice_shares", {}) if isinstance(choice_audit, dict) else {}
    if not isinstance(shares, dict):
        shares = {}
    intervals = {}
    if isinstance(bootstrap, dict):
        overall = bootstrap.get("overall", {}) if isinstance(bootstrap.get("overall"), dict) else {}
        intervals = overall.get("intervals", {}) if isinstance(overall.get("intervals"), dict) else {}
        if not shares:
            point = overall.get("point", {}) if isinstance(overall.get("point"), dict) else {}
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
    rows.sort(key=lambda row: (-(row["share"] or 0), row["choice"]))
    return rows


def audit_statuses(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    choice_validation = artifacts.get("choice_interview_validation") or {}
    persona_coherence = artifacts.get("persona_coherence_audit") or {}
    product_audit = artifacts.get("product_scenario_audit") or {}
    ipf_audit = artifacts.get("ipf_audit") or {}
    rows = [
        {
            "check": "IPF / raking",
            "status": "pass" if ipf_audit.get("converged") is True else "review",
            "detail": f"iterations={ipf_audit.get('iterations_completed', 'n/a')}; warnings={ipf_audit.get('warning_count', 'n/a')}",
        },
        {
            "check": "Persona coherence",
            "status": "pass" if persona_coherence.get("passes_persona_coherence") is True else "review",
            "detail": f"errors={persona_coherence.get('error_count', 'n/a')}; warnings={persona_coherence.get('warning_count', 'n/a')}",
        },
        {
            "check": "Product scenario",
            "status": "pass" if product_audit.get("passes_product_scenario_normalization") is True else "review",
            "detail": f"alternatives={product_audit.get('alternative_count', 'n/a')}; outside={product_audit.get('outside_option_included', 'n/a')}",
        },
        {
            "check": "Choice rows",
            "status": "pass" if choice_validation.get("passes_choice_interview_integrity") is True else "review",
            "detail": f"records={choice_validation.get('record_count', 'n/a')}; errors={choice_validation.get('error_count', 'n/a')}; warnings={choice_validation.get('warning_count', 'n/a')}",
        },
    ]
    return rows


def build_summary(manifest_path: Path, max_reasons: int, max_artifacts: int) -> dict[str, Any]:
    manifest = load_json(manifest_path, {}) or {}
    run_dir = manifest_path.resolve().parent
    root = Path.cwd()

    artifacts = {
        key: load_json(artifact_path(manifest, key, run_dir), {})
        for key in (
            "choice_model_audit",
            "choice_interview_validation",
            "bootstrap_intervals",
            "persona_coherence_audit",
            "ipf_audit",
            "product_scenario_audit",
            "soft_trait_audit",
            "persona_sampling_audit",
            "normalized_choice_scenario",
        )
    }
    choice_results = artifact_path(manifest, "choice_results", run_dir)
    choice_audit = artifacts.get("choice_model_audit") or {}
    bootstrap = artifacts.get("bootstrap_intervals") or {}
    inputs = manifest.get("inputs", {}) if isinstance(manifest.get("inputs"), dict) else {}
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    limitations = []
    boundary = manifest.get("scientific_boundary", {}) if isinstance(manifest.get("scientific_boundary"), dict) else {}
    if isinstance(boundary.get("limitations"), list):
        limitations.extend(str(item) for item in boundary["limitations"][:4])
    if isinstance(choice_audit.get("limitations"), list):
        limitations.extend(str(item) for item in choice_audit["limitations"][:3])

    artifact_list = []
    for key, path_text in sorted(outputs.items()):
        if len(artifact_list) >= max_artifacts:
            break
        artifact_list.append({"name": key, "path": rel(Path(path_text), root)})

    return {
        "report_version": REPORT_VERSION,
        "run_id": manifest.get("run_id"),
        "pipeline_status": manifest.get("status"),
        "created_at": manifest.get("created_at"),
        "inputs": inputs,
        "method": manifest.get("method"),
        "choice_model_method": choice_audit.get("method"),
        "choice_model_calibration_level": boundary.get("choice_model_calibration_level"),
        "record_count": choice_audit.get("record_count") or artifacts.get("choice_interview_validation", {}).get("record_count"),
        "total_weight": choice_audit.get("total_weight") or bootstrap.get("total_weight"),
        "choice_shares": share_rows(choice_audit, bootstrap),
        "confidence_counts": artifacts.get("choice_interview_validation", {}).get("answer_confidence_counts", {}),
        "audit_statuses": audit_statuses(artifacts),
        "top_drivers": weighted_reason_counts(choice_results, "main_drivers", max_reasons),
        "top_barriers": weighted_reason_counts(choice_results, "main_barriers", max_reasons),
        "artifacts": artifact_list,
        "limitations": list(dict.fromkeys(limitations))[:6],
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any]) -> str:
    run_id = summary.get("run_id") or "unknown_run"
    lines: list[str] = [f"# Market Report: {run_id}", ""]
    lines.extend(
        [
            "## Executive Summary",
            "",
            f"- Pipeline status: **{summary.get('pipeline_status', 'n/a')}**",
            f"- Records: **{number(summary.get('record_count'))}**",
            f"- Total weighted population: **{number(summary.get('total_weight'))}**",
            f"- Choice model: **{summary.get('choice_model_method', 'n/a')}**",
            f"- Calibration level: **{summary.get('choice_model_calibration_level', 'n/a')}**",
            "",
        ]
    )

    lines.extend(["## Choice Results", ""])
    choice_rows = [
        [row["choice"], pct(row.get("share")), pct(row.get("p2_5")), pct(row.get("p97_5"))]
        for row in summary.get("choice_shares", [])
    ]
    lines.append(markdown_table(["Choice", "Weighted share", "2.5%", "97.5%"], choice_rows or [["n/a", "n/a", "n/a", "n/a"]]))
    lines.append("")

    lines.extend(["## Audit Status", ""])
    audit_rows = [[row["check"], row["status"], row["detail"]] for row in summary.get("audit_statuses", [])]
    lines.append(markdown_table(["Check", "Status", "Detail"], audit_rows))
    lines.append("")

    lines.extend(["## Main Drivers and Barriers", ""])
    drivers = ", ".join(f"{item['label']} ({number(item['weighted_count'])})" for item in summary.get("top_drivers", [])) or "n/a"
    barriers = ", ".join(f"{item['label']} ({number(item['weighted_count'])})" for item in summary.get("top_barriers", [])) or "n/a"
    lines.extend([f"- Top drivers: {drivers}", f"- Top barriers: {barriers}", ""])

    lines.extend(["## Method Boundary", ""])
    for limitation in summary.get("limitations", []):
        lines.append(f"- {limitation}")
    if not summary.get("limitations"):
        lines.append("- Synthetic outputs are hypotheses, not observed consumer data.")
    lines.append("")

    lines.extend(["## Key Artifacts", ""])
    artifact_rows = [[item["name"], item["path"]] for item in summary.get("artifacts", [])]
    lines.append(markdown_table(["Artifact", "Path"], artifact_rows or [["n/a", "n/a"]]))
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--max-reasons", type=int, default=5)
    parser.add_argument("--max-artifacts", type=int, default=18)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_reasons <= 0:
        raise ValueError("--max-reasons must be positive")
    if args.max_artifacts <= 0:
        raise ValueError("--max-artifacts must be positive")
    manifest = args.manifest.resolve()
    run_dir = manifest.parent
    summary = build_summary(manifest, args.max_reasons, args.max_artifacts)
    output_md = args.output_md or run_dir / "market_report.md"
    output_json = args.output_json or run_dir / "market_report.json"
    write_json(output_json, summary)
    write_text(output_md, render_markdown(summary))
    print(json.dumps({"market_report_md": str(output_md), "market_report_json": str(output_json)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
