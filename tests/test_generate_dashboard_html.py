from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "generate_dashboard_html.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class DashboardHtmlGeneratorTest(unittest.TestCase):
    def test_dashboard_html_embeds_dashboard_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dashboard_data = tmp / "dashboard_data.json"
            output = tmp / "dashboard.html"
            write_json(
                dashboard_data,
                {
                    "dashboard_data_version": "test",
                    "run": {"run_id": "html_test"},
                    "method": {"interview_engine": "rule_based_baseline", "calibration_level": "uncalibrated_rule_based_baseline"},
                    "country_panel": {"respondent_count": 2, "total_weighted_population": 3, "distributions": {}},
                    "results": {"record_count": 2, "choice_shares": [{"choice": "focal_product", "share": 0.6}]},
                    "product_scenario": {"alternatives": []},
                    "quality": {"cards": []},
                    "artifacts": [],
                },
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--dashboard-data", str(dashboard_data), "--output", str(output)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            html = output.read_text(encoding="utf-8")
            self.assertIn("<!doctype html>", html.lower())
            self.assertIn("window.DASHBOARD_DATA", html)
            self.assertIn("html_test", html)
            self.assertIn("dashboard_data.json", html)
            self.assertIn("Self-contained dashboard artifact", html)

    def test_dashboard_html_can_resolve_manifest_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dashboard_data = tmp / "dashboard_data.json"
            manifest = tmp / "manifest.json"
            output = tmp / "dashboard.html"
            write_json(dashboard_data, {"run": {"run_id": "manifest_test"}, "method": {}, "country_panel": {}, "results": {}, "product_scenario": {}, "quality": {}})
            write_json(manifest, {"outputs": {"dashboard_data": str(dashboard_data)}})
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--manifest", str(manifest), "--output", str(output)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue(output.exists())
            self.assertIn("manifest_test", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
