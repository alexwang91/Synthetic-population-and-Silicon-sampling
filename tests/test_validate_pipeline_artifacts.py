from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "validate_pipeline_artifacts.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def make_minimal_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "seed_cells": str(run_dir / "seed_cells.jsonl"),
        "weighted_cells": str(run_dir / "weighted_cells.jsonl"),
        "personas_core": str(run_dir / "personas_core.jsonl"),
        "personas_enriched": str(run_dir / "personas_enriched.jsonl"),
        "normalized_choice_scenario": str(run_dir / "normalized_choice_scenario.json"),
        "choice_results": str(run_dir / "choice_results.jsonl"),
        "choice_model_audit": str(run_dir / "choice_model_audit.json"),
        "choice_interview_validation": str(run_dir / "choice_interview_validation.json"),
        "bootstrap_intervals": str(run_dir / "bootstrap_intervals.json"),
        "market_report_md": str(run_dir / "market_report.md"),
        "market_report_json": str(run_dir / "market_report.json"),
        "ipf_audit": str(run_dir / "ipf_audit.json"),
        "persona_sampling_audit": str(run_dir / "persona_sampling_audit.json"),
        "soft_trait_audit": str(run_dir / "soft_trait_audit.json"),
        "persona_coherence_audit": str(run_dir / "persona_coherence_audit.json"),
        "product_scenario_audit": str(run_dir / "product_scenario_audit.json"),
    }
    write_json(
        run_dir / "manifest.json",
        {
            "status": "passed",
            "run_id": "fake_run",
            "outputs": outputs,
            "steps": [{"step": "fake", "returncode": 0}],
            "scientific_boundary": {
                "pipeline_changes_model_outputs": False,
                "choice_model_calibration_level": "uncalibrated_rule_based_baseline",
                "report_policy": "concise",
                "limitations": ["synthetic hypotheses only"],
            },
        },
    )
    for key in ("seed_cells", "weighted_cells", "personas_core", "personas_enriched", "choice_results"):
        write_text(Path(outputs[key]), json.dumps({"row": 1}) + "\n")
    write_json(Path(outputs["normalized_choice_scenario"]), {"alternatives": [{"id": "A"}, {"id": "none"}]})
    write_json(Path(outputs["choice_model_audit"]), {"record_count": 10, "method": "deterministic_rule_based_random_utility_baseline", "weighted_choice_shares": {"focal_product": 0.6, "competitor": 0.4}})
    write_json(Path(outputs["choice_interview_validation"]), {"passes_choice_interview_integrity": True, "record_count": 10, "error_count": 0, "warning_count": 0})
    write_json(Path(outputs["bootstrap_intervals"]), {"overall": {"intervals": {"focal_product": {"p2_5": 0.5, "p97_5": 0.7}}}})
    write_json(Path(outputs["ipf_audit"]), {"converged": True, "iterations_completed": 4, "warning_count": 0})
    write_json(Path(outputs["persona_sampling_audit"]), {"realized_sample_size": 10})
    write_json(Path(outputs["soft_trait_audit"]), {"record_count": 10})
    write_json(Path(outputs["persona_coherence_audit"]), {"passes_persona_coherence": True, "error_count": 0, "warning_count": 0})
    write_json(Path(outputs["product_scenario_audit"]), {"passes_product_scenario_normalization": True, "alternative_count": 2, "outside_option_included": True, "error_count": 0})
    write_json(Path(outputs["market_report_json"]), {"run_id": "fake_run", "choice_shares": [{"choice": "focal_product", "share": 0.6}], "limitations": ["synthetic hypotheses only"]})
    write_text(Path(outputs["market_report_md"]), "# Market Report: fake_run\n\n## Executive Summary\n\n## Choice Results\n\n## Audit Status\n\n## Method Boundary\n")


class PipelineArtifactValidatorTest(unittest.TestCase):
    def test_minimal_valid_run_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "fake_run"
            make_minimal_run(run_dir)
            audit = run_dir / "pipeline_artifact_validation.json"
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(run_dir), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = json.loads(audit.read_text(encoding="utf-8"))
            self.assertTrue(summary["passes_pipeline_artifact_validation"])
            self.assertEqual(summary["error_count"], 0)

    def test_missing_required_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "fake_run"
            make_minimal_run(run_dir)
            (run_dir / "choice_results.jsonl").unlink()
            audit = run_dir / "pipeline_artifact_validation.json"
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(run_dir / "manifest.json"), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            summary = json.loads(audit.read_text(encoding="utf-8"))
            self.assertFalse(summary["passes_pipeline_artifact_validation"])
            issues = {item["issue"] for item in summary["errors"]}
            self.assertIn("missing_or_empty_required_output", issues)


if __name__ == "__main__":
    unittest.main()
