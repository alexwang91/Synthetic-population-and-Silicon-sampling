from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "validate_persona_coherence.py"
EXPAND_SOFT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "expand_soft_traits.py"


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


class PersonaCoherenceValidatorTest(unittest.TestCase):
    def test_valid_enriched_persona_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            core = tmp / "personas_core.jsonl"
            enriched = tmp / "personas_enriched.jsonl"
            audit = tmp / "coherence_audit.json"

            write_jsonl(
                core,
                [
                    {
                        "persona_id": "RS-000001",
                        "population_weight": 100.0,
                        "hard": {
                            "region": "Belgrade",
                            "sex": "female",
                            "age_band": "35-44",
                            "education_level": "tertiary",
                            "income_decile": "8",
                            "household_size": "3",
                            "settlement_type": "urban",
                            "employment_status": "employed",
                        },
                        "soft": {},
                        "calibration_trace": {},
                    }
                ],
            )

            subprocess.run(
                [
                    sys.executable,
                    str(EXPAND_SOFT),
                    str(core),
                    "--category",
                    "smartwatch",
                    "--category-price-index",
                    "0.7",
                    "--output",
                    str(enriched),
                ],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(enriched), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = json.loads(audit.read_text(encoding="utf-8"))
            self.assertTrue(summary["passes_persona_coherence"])
            self.assertEqual(summary["error_count"], 0)
            self.assertEqual(summary["record_count"], 1)
            self.assertIn("smartwatch", summary["category_counts"])

    def test_invalid_persona_fails_on_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            enriched = tmp / "bad_personas.jsonl"
            audit = tmp / "coherence_audit.json"

            write_jsonl(
                enriched,
                [
                    {
                        "persona_id": "RS-000001",
                        "population_weight": -5,
                        "hard": {"income_decile": "9"},
                        "soft": {
                            "media_habits": {"digital_intensity": 1.2},
                            "shopping_habits": {"online_purchase_readiness": 0.9},
                            "psychographics": {"price_sensitivity": 0.9},
                            "category_priors": {
                                "category": "test",
                                "category_affordability": 0.1,
                                "need_activation": 0.9,
                                "comfortable_price_multiplier": 1.4,
                                "stretch_price_multiplier": 1.1,
                            },
                            "soft_trait_trace": {"method": "manual", "llm_generated": False},
                        },
                        "calibration_trace": {"soft_trait_expansion": {}},
                    }
                ],
            )

            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(enriched), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            summary = json.loads(audit.read_text(encoding="utf-8"))
            self.assertFalse(summary["passes_persona_coherence"])
            issues = {item["issue"] for item in summary["errors"]}
            self.assertIn("invalid_population_weight", issues)
            self.assertIn("score_out_of_bounds", issues)
            self.assertIn("comfortable_multiplier_exceeds_stretch_multiplier", issues)


if __name__ == "__main__":
    unittest.main()
