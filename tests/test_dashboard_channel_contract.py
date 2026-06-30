from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "generate_dashboard_data.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class DashboardChannelContractTest(unittest.TestCase):
    def test_dashboard_reads_aggregate_media_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run = Path(tmpdir) / "run"
            run.mkdir()
            brief = {"country": "Hungary", "audience": "cycling enthusiasts", "category": "smartwatch", "budget": 100000, "currency": "EUR"}
            write_json(run / "channel_plan.json", {"input_brief": brief, "planning_mode": "deterministic_rule_based", "channels": [{"channel_id": "google_search", "name": "Google Search"}]})
            write_json(run / "channel_simulation_results.json", {"input_brief": brief, "channel_results": [{"channel_id": "google_search", "roi": 2.1, "roas": 3.1, "cac": 20, "weighted_conversions": 900, "confidence_interval": [1.8, 2.4]}]})
            write_json(run / "budget_allocation.json", {"input_brief": brief, "recommended_budget_split": [{"channel_id": "google_search", "priority": 1, "budget": 25000, "budget_pct": 0.25, "rationale": "High intent", "execution_advice": "Protect intent", "risk": "low"}], "summary": {"best_channel": "google_search", "holdout_pct": 0.1, "test_budget_pct": 0.15}})
            write_json(run / "manifest.json", {"run_id": "media_contract", "status": "passed", "pipeline_version": "0.2.0", "method": "ai_media_planner_pipeline", "inputs": brief, "outputs": {"channel_plan": str(run / "channel_plan.json"), "channel_simulation_results": str(run / "channel_simulation_results.json"), "budget_allocation": str(run / "budget_allocation.json")}, "steps": [{"step": "audience_panel", "status": "passed"}, {"step": "channel_candidates", "status": "passed"}, {"step": "simulation", "status": "passed"}, {"step": "budget_allocation", "status": "passed"}, {"step": "recommendations", "status": "passed"}], "scientific_boundary": {"choice_model_calibration_level": "uncalibrated_media_planning_simulation", "limitations": ["planning only"]}})
            output = run / "dashboard_data.json"
            result = subprocess.run([sys.executable, str(SCRIPT), str(run / "manifest.json"), "--output", str(output)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            for section in ["input_brief", "workflow_steps", "channel_plan", "channel_results", "budget_recommendation", "run_history"]:
                self.assertIn(section, data)
            self.assertEqual(data["input_brief"]["country"], "Hungary")
            self.assertEqual(len(data["workflow_steps"]), 5)
            self.assertEqual(data["workflow_steps"][0]["status"], "passed")
            rendered = json.dumps(data, ensure_ascii=False)
            self.assertNotIn("raw_llm" + "_response", rendered)
            self.assertNotIn("row_level", rendered)


if __name__ == "__main__":
    unittest.main()
