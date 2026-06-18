from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_scenario_pipeline.py"
CONFIG = REPO_ROOT / "skills" / "weighted-persona-pricing" / "examples" / "serbia_smartwatch_pipeline_config.json"


class ScenarioPipelineRunnerTest(unittest.TestCase):
    def test_pipeline_config_produces_manifest_and_core_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run(
                [sys.executable, str(PIPELINE), str(CONFIG), "--output-root", str(output_root)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

            run_dir = output_root / "serbia_smartwatch_pipeline_demo"
            manifest_path = run_dir / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["method"], "synthetic_respondent_scenario_pipeline")
            self.assertEqual(manifest["interview_engine"], "rule_based_baseline")
            self.assertFalse(manifest["scientific_boundary"]["pipeline_changes_model_outputs"])
            self.assertIn("original_plan_alignment", manifest["scientific_boundary"])
            self.assertIn("report_policy", manifest["scientific_boundary"])
            self.assertIn("token_policy", manifest["scientific_boundary"])
            self.assertIn("acceptance_policy", manifest["scientific_boundary"])
            step_names = [step["step"] for step in manifest["steps"]]
            self.assertEqual(
                step_names,
                [
                    "validate_country_pack",
                    "country_pack_to_cells",
                    "run_ipf",
                    "sample_persona_skeletons",
                    "expand_soft_traits",
                    "validate_persona_coherence",
                    "product_scenario_normalizer",
                    "run_choice_model",
                    "validate_choice_interviews",
                    "bootstrap_choice_intervals",
                    "generate_market_report",
                    "generate_dashboard_data",
                    "validate_pipeline_artifacts",
                ],
            )
            self.assertTrue((run_dir / "choice_results.jsonl").exists())
            self.assertTrue((run_dir / "choice_model_audit.json").exists())
            self.assertTrue((run_dir / "choice_interview_validation.json").exists())
            self.assertTrue((run_dir / "bootstrap_intervals.json").exists())
            self.assertTrue((run_dir / "market_report.md").exists())
            self.assertTrue((run_dir / "market_report.json").exists())
            self.assertTrue((run_dir / "dashboard_data.json").exists())
            self.assertTrue((run_dir / "pipeline_artifact_validation.json").exists())
            self.assertIn("market_report_md", manifest["outputs"])
            self.assertIn("market_report_json", manifest["outputs"])
            self.assertIn("dashboard_data", manifest["outputs"])
            self.assertIn("pipeline_artifact_validation", manifest["outputs"])

            choice_validation = json.loads((run_dir / "choice_interview_validation.json").read_text(encoding="utf-8"))
            self.assertTrue(choice_validation["passes_choice_interview_integrity"])
            self.assertEqual(choice_validation["record_count"], 40)

            report_json = json.loads((run_dir / "market_report.json").read_text(encoding="utf-8"))
            report_md = (run_dir / "market_report.md").read_text(encoding="utf-8")
            self.assertEqual(report_json["run_id"], "serbia_smartwatch_pipeline_demo")
            self.assertIn("# Market Report:", report_md)
            self.assertIn("## Executive Summary", report_md)

            dashboard_data = json.loads((run_dir / "dashboard_data.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard_data["run"]["run_id"], "serbia_smartwatch_pipeline_demo")
            self.assertEqual(dashboard_data["method"]["interview_engine"], "rule_based_baseline")
            self.assertIn("results", dashboard_data)
            self.assertIn("quality", dashboard_data)

            artifact_validation = json.loads((run_dir / "pipeline_artifact_validation.json").read_text(encoding="utf-8"))
            self.assertTrue(artifact_validation["passes_pipeline_artifact_validation"])
            self.assertEqual(artifact_validation["error_count"], 0)
            self.assertEqual(artifact_validation["report_length_policy"], "disabled")

    def test_pipeline_can_stop_after_intermediate_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE),
                    str(CONFIG),
                    "--output-root",
                    str(output_root),
                    "--stop-after",
                    "expand_soft_traits",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

            run_dir = output_root / "serbia_smartwatch_pipeline_demo"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "stopped")
            self.assertTrue((run_dir / "personas_enriched.jsonl").exists())
            self.assertFalse((run_dir / "choice_results.jsonl").exists())
            self.assertFalse((run_dir / "market_report.md").exists())
            self.assertFalse((run_dir / "dashboard_data.json").exists())
            self.assertFalse((run_dir / "pipeline_artifact_validation.json").exists())

    def test_llm_short_all_exports_prompts_and_awaits_responses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            config["run_id"] = "serbia_llm_prompt_export_demo"
            config["interview_engine"] = "llm_short_all"
            config["llm_prompt_limit"] = 5
            config_path = tmp / "llm_config.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output_root = tmp / "runs"
            result = subprocess.run(
                [sys.executable, str(PIPELINE), str(config_path), "--output-root", str(output_root)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

            run_dir = output_root / "serbia_llm_prompt_export_demo"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "awaiting_llm_responses")
            self.assertEqual(manifest["interview_engine"], "llm_short_all")
            step_names = [step["step"] for step in manifest["steps"]]
            self.assertIn("export_llm_choice_prompts", step_names)
            self.assertNotIn("run_choice_model", step_names)
            self.assertTrue((run_dir / "llm_choice_prompts.jsonl").exists())
            self.assertTrue((run_dir / "llm_choice_prompt_audit.json").exists())
            self.assertFalse((run_dir / "choice_results.jsonl").exists())
            prompts = [line for line in (run_dir / "llm_choice_prompts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(prompts), 5)


if __name__ == "__main__":
    unittest.main()
