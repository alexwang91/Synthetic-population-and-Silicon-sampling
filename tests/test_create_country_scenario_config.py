from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "create_country_scenario_config.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class CountryScenarioConfigBuilderTest(unittest.TestCase):
    def test_builder_creates_10000_country_run_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            country_pack = tmp / "country_pack.json"
            product = tmp / "product.json"
            margins = tmp / "margins.json"
            output = tmp / "config.json"
            write_json(
                country_pack,
                {
                    "country_identity": {"country_name": "Testland", "iso2": "TL", "iso3": "TST", "population_year": 2026},
                    "coverage_scope": {"base_population_reference": {"value": 1000}},
                },
            )
            write_json(product, {"scenario_id": "watch_demo", "category": "smartwatch", "alternatives": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}]})
            write_json(
                margins,
                {
                    "separator": "|",
                    "margins": [
                        {"name": "sex", "variables": ["sex"], "targets": {"male": 50.0, "female": 50.0}}
                    ],
                },
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--country-pack",
                    str(country_pack),
                    "--product-scenario",
                    str(product),
                    "--margins-json",
                    str(margins),
                    "--dimension",
                    "sex=male,female",
                    "--dimension",
                    "region=North,South",
                    "--run-id",
                    "testland_watch_10000",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(config["run_id"], "testland_watch_10000")
            self.assertEqual(config["sample_size"], 10000)
            self.assertEqual(config["dashboard_medium_sample_size"], 1000)
            self.assertEqual(config["dashboard_deep_sample_size"], 100)
            self.assertTrue(config["generate_dashboard_data"])
            self.assertTrue(config["generate_dashboard_html"])
            self.assertEqual(config["interview_engine"], "llm_short_all")
            self.assertTrue(config["country_run_policy"]["regenerate_panel_from_country_pack"])
            self.assertTrue(config["country_run_policy"]["no_static_persona_panel_input"])
            self.assertIn("margins_inline", config)
            self.assertNotIn("personas_enriched", config)
            self.assertNotIn("choice_results", config)

    def test_builder_supports_rule_based_baseline_for_smoke_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            country_pack = tmp / "country_pack.json"
            product = tmp / "product.json"
            margins = tmp / "margins.json"
            output = tmp / "config.json"
            write_json(country_pack, {"country_identity": {"country_name": "Testland", "iso2": "TL"}})
            write_json(product, {"scenario_id": "demo", "category": "smartwatch"})
            write_json(margins, {"margins": [{"name": "sex", "variables": ["sex"], "targets": {"male": 1, "female": 1}}]})
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--country-pack",
                    str(country_pack),
                    "--product-scenario",
                    str(product),
                    "--margins-json",
                    str(margins),
                    "--dimension",
                    "sex=male,female",
                    "--sample-size",
                    "40",
                    "--interview-engine",
                    "rule_based_baseline",
                    "--run-id",
                    "smoke",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            config = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(config["sample_size"], 40)
            self.assertEqual(config["interview_engine"], "rule_based_baseline")
            self.assertTrue(config["generate_dashboard_html"])
            self.assertIn("choice_mode", config)
            self.assertNotIn("llm_order_policy", config)


if __name__ == "__main__":
    unittest.main()
