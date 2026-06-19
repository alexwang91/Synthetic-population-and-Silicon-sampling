from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_no_static_panel_dependency.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class CountryRunDependencyValidatorTest(unittest.TestCase):
    def test_valid_country_run_config_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = tmp / "valid.json"
            audit = tmp / "audit.json"
            write_json(
                config,
                {
                    "run_id": "valid",
                    "country_pack": "country.json",
                    "dimensions": {"sex": ["male", "female"]},
                    "margins_inline": {"margins": []},
                    "sample_size": 10000,
                    "product_scenario": "product.json",
                    "category": "smartwatch",
                    "category_price_index": 0.7,
                    "country_run_policy": {
                        "regenerate_panel_from_country_pack": True,
                        "no_static_persona_panel_input": True,
                        "medium_and_deep_samples_derived_from_active_run": True,
                    },
                },
            )
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(config), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = json.loads(audit.read_text(encoding="utf-8"))
            self.assertTrue(summary["passes_country_run_dependency_validation"])
            self.assertEqual(summary["error_count"], 0)

    def test_prior_persona_input_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = tmp / "bad.json"
            audit = tmp / "audit.json"
            write_json(
                config,
                {
                    "run_id": "bad",
                    "country_pack": "country.json",
                    "dimensions": {"sex": ["male", "female"]},
                    "margins_inline": {"margins": []},
                    "sample_size": 10000,
                    "product_scenario": "product.json",
                    "category": "smartwatch",
                    "category_price_index": 0.7,
                    "personas_enriched": "old/personas_enriched.jsonl",
                    "country_run_policy": {
                        "regenerate_panel_from_country_pack": True,
                        "no_static_persona_panel_input": True,
                    },
                },
            )
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(config), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            summary = json.loads(audit.read_text(encoding="utf-8"))
            issues = {item["issue"] for item in summary["errors"]}
            self.assertIn("blocked_prior_panel_inputs", issues)

    def test_demo_sized_config_warns_but_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = tmp / "demo.json"
            audit = tmp / "audit.json"
            write_json(
                config,
                {
                    "run_id": "demo",
                    "country_pack": "country.json",
                    "dimensions": {"sex": ["male", "female"]},
                    "margins_inline": {"margins": []},
                    "sample_size": 40,
                    "product_scenario": "product.json",
                    "category": "smartwatch",
                    "category_price_index": 0.7,
                    "country_run_policy": {
                        "regenerate_panel_from_country_pack": True,
                        "no_static_persona_panel_input": True,
                    },
                },
            )
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(config), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = json.loads(audit.read_text(encoding="utf-8"))
            issues = {item["issue"] for item in summary["warnings"]}
            self.assertIn("below_production_panel_size", issues)


if __name__ == "__main__":
    unittest.main()
