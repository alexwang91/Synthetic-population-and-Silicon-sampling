#!/usr/bin/env python3
"""Validate a completed scenario pipeline run folder.

This is an acceptance-check layer. It verifies that key artifacts exist, JSON
artifacts parse, critical audit checks pass, and the manifest preserves
scientific boundaries.

Report length is not a default hard limit. If `--max-report-lines` is positive,
an overlong report is emitted as a warning so callers can decide whether to
fail with `--fail-on-warning`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VALIDATOR_VERSION = "0.1.0"
BASE_REQUIRED_OUTPUT_KEYS = [
    "seed_cells",
    "weighted_cells",
    "personas_core",
    "personas_enriched",
    "normalized_choice_scenario",
    "choice_results",
    "choice_interview_validation",
    "bootstrap_intervals",
    "market_report_md",
    "market_report_json",
]
ENGINE_REQUIRED_OUTPUT_KEYS = {
    "rule_based_baseline": ["choice_model_audit"],
    "llm_short_all": ["llm_choice_prompts", "llm_choice_prompt_audit", "llm_choice_interview_audit", "llm_choice_quality_audit"],
}
JSON_OUTPUT_KEYS = [
    "ipf_audit",
    "persona_sampling_audit",
    "soft_trait_audit",
    "persona_coherence_audit",
    "product_scenario_audit",
    "choice_model_audit",
    "llm_choice_prompt_audit",
    "llm_choice_interview_audit",
    "llm_choice_quality_audit",
    "choice_interview_validation",
    "bootstrap_intervals",
    "market_report_json",
]


class IssueSink:
    def __init__(self) -> None:
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    def error(self, issue: str, **extra: Any) -> None:
        payload = {"issue": issue}
        payload.update(extra)
        self.errors.append(payload)

    def warning(self, issue: str, **extra: Any) -> None:
        payload = {"issue": issue}
        payload.update(extra)
        self.warnings.append(payload)


def required_output_keys(manifest: dict[str, Any]) -> list[str]:
    engine = str(manifest.get("interview_engine", "rule_based_baseline"))
    return BASE_REQUIRED_OUTPUT_KEYS + ENGINE_REQUIRED_OUTPUT_KEYS.get(engine, [])


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, "file_not_found"
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"
    if not isinstance(value, dict):
        return None, "json_root_not_object"
    return value, None


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_manifest(path: Path) -> Path:
    if path.is_dir():
        return path / "manifest.json"
    return path


def resolve_output_path(raw: str, run_dir: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    candidate = run_dir / path
    if candidate.exists():
        return candidate
    return path


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8-sig").splitlines())


def nonempty_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def check_manifest(manifest: dict[str, Any], manifest_path: Path, sink: IssueSink) -> None:
    if manifest.get("status") != "passed":
        sink.error("manifest_status_not_passed", status=manifest.get("status"))
    engine = manifest.get("interview_engine", "rule_based_baseline")
    if engine not in ENGINE_REQUIRED_OUTPUT_KEYS:
        sink.error("unsupported_interview_engine", interview_engine=engine)
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        sink.error("manifest_missing_steps")
    else:
        failed_steps = [step for step in steps if isinstance(step, dict) and step.get("returncode") != 0]
        if failed_steps:
            sink.error("manifest_contains_failed_steps", failed_steps=[step.get("step") for step in failed_steps])

    boundary = manifest.get("scientific_boundary")
    if not isinstance(boundary, dict):
        sink.error("manifest_missing_scientific_boundary")
        return
    if boundary.get("pipeline_changes_model_outputs") is not False:
        sink.error("pipeline_boundary_allows_output_mutation", value=boundary.get("pipeline_changes_model_outputs"))
    if not boundary.get("choice_model_calibration_level"):
        sink.warning("missing_choice_model_calibration_level")
    if not boundary.get("report_policy"):
        sink.warning("missing_report_policy")
    if not boundary.get("token_policy"):
        sink.warning("missing_token_policy")
    if not boundary.get("original_plan_alignment"):
        sink.warning("missing_original_plan_alignment")
    if not boundary.get("llm_risk_controls"):
        sink.warning("missing_llm_risk_controls")
    limitations = boundary.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        sink.warning("missing_scientific_limitations")


def load_outputs(manifest: dict[str, Any], run_dir: Path, sink: IssueSink) -> dict[str, Path]:
    raw_outputs = manifest.get("outputs")
    if not isinstance(raw_outputs, dict):
        sink.error("manifest_outputs_not_object")
        return {}
    outputs: dict[str, Path] = {}
    for key, raw in raw_outputs.items():
        if isinstance(raw, str) and raw:
            outputs[key] = resolve_output_path(raw, run_dir)
    for key in required_output_keys(manifest):
        if key not in outputs:
            sink.error("missing_required_output_key", key=key)
        elif not nonempty_file(outputs[key]):
            sink.error("missing_or_empty_required_output", key=key, path=str(outputs[key]))
    return outputs


def check_json_outputs(outputs: dict[str, Path], sink: IssueSink) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for key in JSON_OUTPUT_KEYS:
        path = outputs.get(key)
        if path is None:
            continue
        value, error = load_json(path)
        if error:
            sink.error("json_artifact_invalid", key=key, path=str(path), error=error)
        elif value is not None:
            loaded[key] = value
    return loaded


def check_audits(manifest: dict[str, Any], artifacts: dict[str, dict[str, Any]], sink: IssueSink) -> None:
    engine = str(manifest.get("interview_engine", "rule_based_baseline"))
    ipf = artifacts.get("ipf_audit", {})
    if ipf and ipf.get("converged") is not True:
        sink.error("ipf_not_converged", converged=ipf.get("converged"), warnings=ipf.get("warning_count"))
    if isinstance(ipf.get("warning_count"), int) and ipf["warning_count"] > 0:
        sink.warning("ipf_has_warnings", warning_count=ipf["warning_count"])

    coherence = artifacts.get("persona_coherence_audit", {})
    if coherence and coherence.get("passes_persona_coherence") is not True:
        sink.error("persona_coherence_failed", errors=coherence.get("error_count"), warnings=coherence.get("warning_count"))
    if isinstance(coherence.get("warning_count"), int) and coherence["warning_count"] > 0:
        sink.warning("persona_coherence_has_warnings", warning_count=coherence["warning_count"])

    product = artifacts.get("product_scenario_audit", {})
    if product and product.get("passes_product_scenario_normalization") is not True:
        sink.error("product_scenario_normalization_failed", errors=product.get("error_count"), warnings=product.get("warnings"))

    choices = artifacts.get("choice_interview_validation", {})
    if choices and choices.get("passes_choice_interview_integrity") is not True:
        sink.error("choice_interview_validation_failed", errors=choices.get("error_count"), warnings=choices.get("warning_count"))
    if choices and choices.get("record_count", 0) <= 0:
        sink.error("choice_validation_has_no_records", record_count=choices.get("record_count"))

    if engine == "rule_based_baseline":
        choice_model = artifacts.get("choice_model_audit", {})
        if choice_model and choice_model.get("record_count", 0) <= 0:
            sink.error("choice_model_has_no_records", record_count=choice_model.get("record_count"))
        if choice_model and choice_model.get("method") != "deterministic_rule_based_random_utility_baseline":
            sink.warning("unexpected_choice_model_method", method=choice_model.get("method"))
    elif engine == "llm_short_all":
        llm_audit = artifacts.get("llm_choice_interview_audit", {})
        if llm_audit and llm_audit.get("coverage_rate", 0) < 1.0:
            sink.warning("llm_choice_interview_coverage_below_one", coverage_rate=llm_audit.get("coverage_rate"))
        if llm_audit and llm_audit.get("response_count", 0) <= 0:
            sink.error("llm_choice_interview_has_no_responses", response_count=llm_audit.get("response_count"))
        quality = artifacts.get("llm_choice_quality_audit", {})
        if quality and quality.get("passes_llm_choice_quality_validation") is not True:
            sink.error("llm_choice_quality_failed", errors=quality.get("error_count"), warnings=quality.get("warning_count"))
        if quality and isinstance(quality.get("warning_count"), int) and quality["warning_count"] > 0:
            sink.warning("llm_choice_quality_has_warnings", warning_count=quality["warning_count"])

    report = artifacts.get("market_report_json", {})
    if report and not report.get("choice_shares"):
        sink.warning("market_report_missing_choice_shares")
    if report and not report.get("limitations"):
        sink.warning("market_report_missing_limitations")


def check_report(outputs: dict[str, Path], max_report_lines: int, sink: IssueSink) -> None:
    report_md = outputs.get("market_report_md")
    if not report_md:
        return
    try:
        lines = line_count(report_md)
    except FileNotFoundError:
        sink.error("market_report_missing", path=str(report_md))
        return
    if max_report_lines > 0 and lines > max_report_lines:
        sink.warning("market_report_long", lines=lines, max_report_lines=max_report_lines, path=str(report_md))
    text = report_md.read_text(encoding="utf-8-sig")
    for heading in ("## Executive Summary", "## Choice Results", "## Audit Status", "## Method Boundary"):
        if heading not in text:
            sink.warning("market_report_missing_expected_heading", heading=heading)


def validate_pipeline(path: Path, max_report_lines: int) -> dict[str, Any]:
    sink = IssueSink()
    manifest_path = resolve_manifest(path)
    run_dir = manifest_path.parent
    manifest, manifest_error = load_json(manifest_path)
    if manifest_error or manifest is None:
        sink.error("manifest_invalid", path=str(manifest_path), error=manifest_error)
        return summary(manifest_path, {}, {}, sink, max_report_lines)

    check_manifest(manifest, manifest_path, sink)
    outputs = load_outputs(manifest, run_dir, sink)
    artifacts = check_json_outputs(outputs, sink)
    check_audits(manifest, artifacts, sink)
    check_report(outputs, max_report_lines, sink)
    return summary(manifest_path, manifest, outputs, sink, max_report_lines)


def summary(manifest_path: Path, manifest: dict[str, Any], outputs: dict[str, Path], sink: IssueSink, max_report_lines: int) -> dict[str, Any]:
    required_keys = required_output_keys(manifest) if manifest else BASE_REQUIRED_OUTPUT_KEYS
    return {
        "validator_version": VALIDATOR_VERSION,
        "run_id": manifest.get("run_id"),
        "interview_engine": manifest.get("interview_engine"),
        "manifest": str(manifest_path),
        "max_report_lines": max_report_lines,
        "report_length_policy": "disabled" if max_report_lines <= 0 else "warning_only",
        "required_output_count": len(required_keys),
        "observed_output_count": len(outputs),
        "error_count": len(sink.errors),
        "warning_count": len(sink.warnings),
        "errors": sink.errors[:200],
        "warnings": sink.warnings[:200],
        "passes_pipeline_artifact_validation": len(sink.errors) == 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_or_manifest", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--max-report-lines", type=int, default=0, help="0 disables report length checks; positive values emit warnings only.")
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_pipeline(args.run_or_manifest, args.max_report_lines)
    if args.audit:
        write_json(args.audit, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["error_count"] > 0:
        return 1
    if args.fail_on_warning and result["warning_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
