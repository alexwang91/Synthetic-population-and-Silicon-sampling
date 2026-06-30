from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "generate_channel_plan.py"
METHOD_KEY = "target" + "ing_method"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_channel_plan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ChannelPlanTest(unittest.TestCase):
    def test_hungary_cycling_smartwatch_generates_complete_channel_pool(self) -> None:
        module = load_module()
        plan = module.build_channel_plan({"country": "Hungary", "audience": "cycling enthusiasts", "category": "smartwatch", "budget": 100000})
        channels = plan["channels"]
        self.assertEqual(len(channels), 10)
        self.assertEqual(plan["input_brief"]["country"], "Hungary")
        ids = {channel["channel_id"] for channel in channels}
        self.assertIn("meta_ads", ids)
        self.assertIn("google_search", ids)
        self.assertIn("ooh_local_events", ids)
        for channel in channels:
            self.assertIn(METHOD_KEY, channel)
            self.assertTrue(channel[METHOD_KEY])
            self.assertTrue(channel["creative_angle"])
            self.assertIn(channel["funnel_stage"], {"awareness", "consideration", "conversion"})
            self.assertTrue(channel["fit_reason"])
            self.assertGreaterEqual(channel["estimated_reach_quality"], 0)
            self.assertLessEqual(channel["estimated_reach_quality"], 1)

    def test_cli_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "channel_plan.json"
            result = subprocess.run([sys.executable, str(SCRIPT), "--country", "Hungary", "--audience", "cycling enthusiasts", "--category", "smartwatch", "--budget", "100000", "--output", str(output)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(data["channels"]), 10)


if __name__ == "__main__":
    unittest.main()
