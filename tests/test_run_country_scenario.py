from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_country_scenario.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class CountryScenarioRunnerTest(unittest.TestCase):
    def test_config_only_creates_valid_country_run_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            country = tmp / "country.json"
            product = tmp / "product.json"
            margins = tmp / "margins.json"
            config = tmp / "config.json"
            audit = tmp / "audit.json"
            write_json(country, {"country_identity": {"country_name": "Testland", "iso2": "TL"}})
            write_json(product, {"scenario_id": "demo", "category": "smartwatch"})
            write_json(margins, {"margins": [{"name": "sex", "variables": ["sex"], "targets": {"male": 1, "female": 1}}]})
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--country-pack",
                    str(country),
                    "--product-scenario",
                    str(product),
                    "--margins-json",
                    str(margins),
                    "--dimension",
                    "sex=male,female",
                    "--run-id",
                    "testland_config_only",
                    "--config-output",
                    str(config),
                    "--country-run-audit",
                    str(audit),
                    "--config-only",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "config_created")
            generated = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(generated["sample_size"], 10000)
            self.assertEqual(generated["dashboard_medium_sample_size"], 1000)
            self.assertEqual(generated["dashboard_deep_sample_size"], 100)
            self.assertTrue(generated["country_run_policy"]["regenerate_panel_from_country_pack"])
            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            self.assertTrue(audit_data["passes_country_run_dependency_validation"])


if __name__ == "__main__":
    unittest.main()
