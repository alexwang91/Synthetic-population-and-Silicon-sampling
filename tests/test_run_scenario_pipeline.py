from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_scenario_pipeline.py"


class ScenarioPipelineRunnerTest(unittest.TestCase):
    def test_minimal_media_planner_cli_produces_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run([
                sys.executable,
                str(PIPELINE),
                "--country", "Hungary",
                "--audience", "cycling enthusiasts",
                "--category", "smartwatch",
                "--budget", "100000",
                "--output-root", str(output_root),
                "--run-id", "hungary_cycling_smartwatch_test",
            ], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            run_dir = output_root / "hungary_cycling_smartwatch_test"
            required = ["channel_plan.json", "channel_simulation_results.json", "budget_allocation.json", "dashboard_data.json", "market_report.md", "manifest.json"]
            for name in required:
                self.assertTrue((run_dir / name).exists(), name)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["method"], "ai_media_planner_pipeline")
            steps = [step["step"] for step in manifest["steps"]]
            for step in ["audience_panel", "channel_candidates", "simulation", "budget_allocation", "recommendations"]:
                self.assertIn(step, steps)
            dashboard = json.loads((run_dir / "dashboard_data.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["input_brief"]["country"], "Hungary")
            self.assertEqual(len(dashboard["workflow_steps"]), 5)
            self.assertTrue(dashboard["budget_recommendation"]["recommended_budget_split"])


if __name__ == "__main__":
    unittest.main()
