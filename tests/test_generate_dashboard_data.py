from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "generate_dashboard_data.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class DashboardDataGeneratorTest(unittest.TestCase):
    def test_dashboard_data_contains_results_method_quality_segments_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            run_dir.mkdir()
            outputs = {
                "personas_enriched": str(run_dir / "personas_enriched.jsonl"),
                "choice_results": str(run_dir / "choice_results.jsonl"),
                "choice_model_audit": str(run_dir / "choice_model_audit.json"),
                "choice_interview_validation": str(run_dir / "choice_interview_validation.json"),
                "bootstrap_intervals": str(run_dir / "bootstrap_intervals.json"),
                "persona_coherence_audit": str(run_dir / "persona_coherence_audit.json"),
                "ipf_audit": str(run_dir / "ipf_audit.json"),
                "product_scenario_audit": str(run_dir / "product_scenario_audit.json"),
                "normalized_choice_scenario": str(run_dir / "normalized_choice_scenario.json"),
                "pipeline_artifact_validation": str(run_dir / "pipeline_artifact_validation.json"),
                "market_report_json": str(run_dir / "market_report.json"),
            }
            write_json(
                run_dir / "manifest.json",
                {
                    "run_id": "dashboard_fake_run",
                    "status": "passed",
                    "pipeline_version": "0.1.0",
                    "created_at": "2026-06-19T00:00:00+00:00",
                    "method": "synthetic_respondent_scenario_pipeline",
                    "interview_engine": "rule_based_baseline",
                    "inputs": {"category": "smartwatch", "llm_order_policy": "canonical", "llm_prompt_variant": "tradeoff"},
                    "outputs": outputs,
                    "scientific_boundary": {
                        "choice_model_calibration_level": "uncalibrated_rule_based_baseline",
                        "original_plan_alignment": "representative weighted respondents each produce a discrete choice",
                        "llm_risk_controls": ["baseline"],
                        "limitations": ["synthetic hypotheses only"],
                    },
                },
            )
            write_jsonl(
                run_dir / "personas_enriched.jsonl",
                [
                    {"persona_id": "P1", "population_weight": 2.0, "hard": {"region": "Belgrade", "sex": "female", "income_decile": "8", "settlement_type": "urban"}, "soft": {"psychographics": {"price_sensitivity": 0.4, "risk_aversion": 0.2}, "media_habits": {"digital_intensity": 0.9}}},
                    {"persona_id": "P2", "population_weight": 1.0, "hard": {"region": "Vojvodina", "sex": "male", "income_decile": "3", "settlement_type": "rural"}, "soft": {"psychographics": {"price_sensitivity": 0.8, "risk_aversion": 0.7}, "media_habits": {"digital_intensity": 0.3}}},
                ],
            )
            write_jsonl(
                run_dir / "choice_results.jsonl",
                [
                    {"persona_id": "P1", "population_weight": 2.0, "choice": "focal_product", "main_drivers": ["driver_a"], "main_barriers": ["barrier_a"], "answer_confidence": "medium"},
                    {"persona_id": "P2", "population_weight": 1.0, "choice": "competitor", "main_drivers": ["driver_b"], "main_barriers": ["barrier_b"], "answer_confidence": "high"},
                ],
            )
            write_json(run_dir / "choice_model_audit.json", {"method": "deterministic_rule_based_random_utility_baseline", "record_count": 2, "total_weight": 3.0, "weighted_choice_shares": {"focal_product": 0.667, "competitor": 0.333}})
            write_json(run_dir / "choice_interview_validation.json", {"passes_choice_interview_integrity": True, "record_count": 2, "error_count": 0, "warning_count": 0, "answer_confidence_counts": {"medium": 1, "high": 1}})
            write_json(run_dir / "bootstrap_intervals.json", {"overall": {"intervals": {"focal_product": {"p2_5": 0.5, "p97_5": 0.8}, "competitor": {"p2_5": 0.2, "p97_5": 0.5}}}})
            write_json(run_dir / "persona_coherence_audit.json", {"passes_persona_coherence": True, "error_count": 0, "warning_count": 0})
            write_json(run_dir / "ipf_audit.json", {"converged": True, "iterations_completed": 3, "warning_count": 0})
            write_json(run_dir / "product_scenario_audit.json", {"passes_product_scenario_normalization": True, "alternative_count": 3, "outside_option_included": True})
            write_json(run_dir / "normalized_choice_scenario.json", {"scenario_id": "demo", "category": "smartwatch", "currency": "EUR", "choice_task_type": "discrete_choice_cbc_style", "alternatives": [{"id": "A", "name": "A", "price": 100, "is_outside_option": False}, {"id": "B", "name": "B", "price": 120, "is_outside_option": False}]})
            write_json(run_dir / "pipeline_artifact_validation.json", {"passes_pipeline_artifact_validation": True, "error_count": 0, "warning_count": 0})
            write_json(run_dir / "market_report.json", {"run_id": "dashboard_fake_run"})

            output = run_dir / "dashboard_data.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(run_dir / "manifest.json"), "--output", str(output), "--medium-sample-size", "1", "--deep-sample-size", "1"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["run"]["run_id"], "dashboard_fake_run")
            self.assertEqual(data["method"]["interview_engine"], "rule_based_baseline")
            self.assertEqual(data["product_scenario"]["scenario_id"], "demo")
            self.assertEqual(len(data["results"]["choice_shares"]), 2)
            self.assertTrue(data["quality"]["cards"])
            self.assertEqual(data["results"]["top_drivers"][0]["label"], "driver_a")
            self.assertEqual(data["country_panel"]["respondent_count"], 2)
            self.assertIn("region", data["country_panel"]["distributions"])
            self.assertTrue(data["archetypes"])
            self.assertIn("region", data["filter_options"])
            self.assertTrue(data["segment_choice_cube"])
            self.assertTrue(data["reason_cube"])
            self.assertEqual(data["sample_layers"]["quantitative_panel"]["selected_count"], 2)
            self.assertEqual(data["sample_layers"]["medium_explanation_sample"]["selected_count"], 1)
            self.assertEqual(data["sample_layers"]["deep_case_sample"]["selected_count"], 1)
            self.assertEqual(len(data["sample_layers"]["deep_case_cards"]), 1)


if __name__ == "__main__":
    unittest.main()
