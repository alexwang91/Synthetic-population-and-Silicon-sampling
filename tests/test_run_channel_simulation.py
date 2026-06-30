from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "generate_channel_plan.py"
SIM_SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / ("run_channel_" + "simulation.py")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ChannelSimulationTest(unittest.TestCase):
    def test_outputs_roi_roas_cac_and_interval_for_every_channel(self) -> None:
        planner = load(PLAN_SCRIPT, "planner")
        simulator = load(SIM_SCRIPT, "simulator")
        plan = planner.build_channel_plan({"country": "Hungary", "audience": "cycling enthusiasts", "category": "smartwatch", "budget": 100000})
        result = simulator.build_simulation(plan, budget=100000)
        self.assertEqual(result["panel_summary"]["llm_dependency"], "none_by_default")
        self.assertEqual(len(result["channel_results"]), 10)
        for row in result["channel_results"]:
            self.assertIn("roi", row)
            self.assertIn("roas", row)
            self.assertIn("cac", row)
            self.assertIn("weighted_conversions", row)
            self.assertEqual(len(row["confidence_interval"]), 2)
            self.assertGreater(row["estimated_reach"], 0)
            self.assertGreaterEqual(row["weighted_conversions"], 0)

    def test_cli_writes_run_folder_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / "channel_plan.json"
            output = tmp / "channel_simulation_results.json"
            subprocess.run([sys.executable, str(PLAN_SCRIPT), "--country", "Hungary", "--audience", "cycling enthusiasts", "--category", "smartwatch", "--budget", "100000", "--output", str(plan_path)], cwd=REPO_ROOT, check=True)
            result = subprocess.run([sys.executable, str(SIM_SCRIPT), str(plan_path), "--budget", "100000", "--output", str(output)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(data["channel_results"])


if __name__ == "__main__":
    unittest.main()
