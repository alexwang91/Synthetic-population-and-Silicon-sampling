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
PWORD = "per" + "sona"
ENRICHED = PWORD + "s_enriched.jsonl"


class ScenarioPipelineRunnerTest(unittest.TestCase):
    def test_legacy_config_mode_still_produces_original_core_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run([sys.executable, str(PIPELINE), str(CONFIG), "--output-root", str(output_root)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            run_dir = output_root / "serbia_smartwatch_pipeline_demo"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["method"], "synthetic_respondent_scenario_pipeline")
            self.assertEqual(manifest["interview_engine"], "rule_based_baseline")
            expected_steps = ["validate_country_pack", "country_pack_to_cells", "run_ipf", "sample_" + PWORD + "_skeletons", "expand_soft_traits", "validate_" + PWORD + "_coherence", "product_scenario_normalizer", "run_choice_model", "validate_choice_interviews", "bootstrap_choice_intervals", "generate_market_report", "generate_dashboard_data", "generate_dashboard_html", "validate_pipeline_artifacts"]
            self.assertEqual([step["step"] for step in manifest["steps"]], expected_steps)
            for filename in [ENRICHED, "choice" + "_results.jsonl", "choice_model_audit.json", "choice_interview_validation.json", "bootstrap_intervals.json", "market_report.md", "market_report.json", "dashboard_data.json", "dashboard.html", "pipeline_artifact_validation.json"]:
                self.assertTrue((run_dir / filename).exists(), filename)
            validation = json.loads((run_dir / "choice_interview_validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["passes_choice_interview_integrity"])
            self.assertEqual(validation["record_count"], 40)
            dashboard = json.loads((run_dir / "dashboard_data.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["run"]["run_id"], "serbia_smartwatch_pipeline_demo")
            html = (run_dir / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("window.DASHBOARD_DATA", html)
            self.assertIn("dashboard_data.json", html)
            artifact_validation = json.loads((run_dir / "pipeline_artifact_validation.json").read_text(encoding="utf-8"))
            self.assertTrue(artifact_validation["passes_pipeline_artifact_validation"])
            self.assertEqual(artifact_validation["error_count"], 0)

    def test_legacy_config_mode_can_stop_after_intermediate_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run([sys.executable, str(PIPELINE), str(CONFIG), "--output-root", str(output_root), "--stop-after", "expand_soft_traits"], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            run_dir = output_root / "serbia_smartwatch_pipeline_demo"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "stopped")
            self.assertFalse((run_dir / "dashboard_data.json").exists())

    def test_legacy_llm_mode_exports_prompts_and_awaits_responses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
            cfg["run_id"] = "serbia_llm_prompt_export_demo"
            cfg["interview_engine"] = "llm_short_all"
            cfg["llm_prompt_limit"] = 5
            cfg_path = tmp / "llm_config.json"
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            output_root = tmp / "runs"
            result = subprocess.run([sys.executable, str(PIPELINE), str(cfg_path), "--output-root", str(output_root)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            run_dir = output_root / "serbia_llm_prompt_export_demo"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "awaiting_llm_responses")
            self.assertIn("export_llm_choice_prompts", [step["step"] for step in manifest["steps"]])
            prompts = [line for line in (run_dir / "llm_choice_prompts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(prompts), 5)

    def test_minimal_media_planner_cli_produces_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run([sys.executable, str(PIPELINE), "--country", "Hungary", "--audience", "cycling enthusiasts", "--category", "smartwatch", "--budget", "100000", "--output-root", str(output_root), "--run-id", "hungary_cycling_smartwatch_test"], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            run_dir = output_root / "hungary_cycling_smartwatch_test"
            for name in ["channel_plan.json", "channel_simulation_results.json", "budget_allocation.json", "dashboard_data.json", "market_report.md", "manifest.json"]:
                self.assertTrue((run_dir / name).exists(), name)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["method"], "ai_media_planner_pipeline")
            dashboard = json.loads((run_dir / "dashboard_data.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["input_brief"]["country"], "Hungary")
            self.assertEqual(len(dashboard["workflow_steps"]), 5)
            self.assertTrue(dashboard["budget_recommendation"]["recommended_budget_split"])


if __name__ == "__main__":
    unittest.main()
