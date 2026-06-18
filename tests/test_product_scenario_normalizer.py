from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "product_scenario_normalizer.py"
EXAMPLE = REPO_ROOT / "skills" / "weighted-persona-pricing" / "examples" / "smartwatch_product_scenario.json"


class ProductScenarioNormalizerTest(unittest.TestCase):
    def test_smartwatch_example_normalizes_to_choice_set_with_outside_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            output = tmp / "choice_scenario.json"
            audit = tmp / "choice_scenario_audit.json"

            subprocess.run(
                [sys.executable, str(NORMALIZER), str(EXAMPLE), "--output", str(output), "--audit", str(audit)],
                check=True,
                cwd=REPO_ROOT,
            )

            scenario = json.loads(output.read_text(encoding="utf-8"))
            audit_data = json.loads(audit.read_text(encoding="utf-8"))

            self.assertEqual(scenario["choice_task_type"], "discrete_choice_cbc_style")
            self.assertEqual(scenario["category"], "smartwatch")
            self.assertEqual(len(scenario["alternatives"]), 3)
            self.assertTrue(scenario["choice_set_policy"]["outside_option_included"])
            self.assertTrue(audit_data["passes_product_scenario_normalization"])
            self.assertEqual(audit_data["alternative_count"], 3)

            by_id = {item["id"]: item for item in scenario["alternatives"]}
            self.assertIn("A", by_id)
            self.assertIn("B", by_id)
            self.assertIn("none", by_id)
            self.assertTrue(by_id["none"]["is_outside_option"])
            self.assertEqual(by_id["A"]["normalized_attributes"]["price_index"], 0.0)
            self.assertEqual(by_id["B"]["normalized_attributes"]["price_index"], 1.0)
            for alternative in scenario["alternatives"]:
                attrs = alternative["normalized_attributes"]
                for field in ("price_index", "brand_strength", "feature_score", "warranty_score", "risk_score", "outside_option_constant"):
                    self.assertGreaterEqual(attrs[field], 0.0)
                    self.assertLessEqual(attrs[field], 1.0)

    def test_duplicate_alternative_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            scenario = tmp / "bad.json"
            output = tmp / "out.json"
            scenario.write_text(
                json.dumps(
                    {
                        "category": "test",
                        "currency": "EUR",
                        "alternatives": [
                            {"id": "A", "name": "One", "price": 10},
                            {"id": "A", "name": "Two", "price": 12},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(NORMALIZER), str(scenario), "--output", str(output)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate alternative id", result.stderr)

    def test_no_outside_option_mode_returns_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            output = tmp / "choice_scenario.json"
            audit = tmp / "audit.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(NORMALIZER),
                    str(EXAMPLE),
                    "--no-outside-option",
                    "--output",
                    str(output),
                    "--audit",
                    str(audit),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            self.assertFalse(audit_data["passes_product_scenario_normalization"])
            self.assertFalse(audit_data["outside_option_included"])


if __name__ == "__main__":
    unittest.main()
