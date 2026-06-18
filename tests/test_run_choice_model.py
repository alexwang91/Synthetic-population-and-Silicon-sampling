from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COUNTRY_PACK = REPO_ROOT / "skills" / "country-pack-builder" / "examples" / "RS_country_pack_v0_1.json"
PRODUCT_SCENARIO = REPO_ROOT / "skills" / "weighted-persona-pricing" / "examples" / "smartwatch_product_scenario.json"
TO_CELLS = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "country_pack_to_cells.py"
RUN_IPF = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "run_ipf.py"
SAMPLE_PERSONAS = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "sample_persona_skeletons.py"
EXPAND_SOFT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "expand_soft_traits.py"
VALIDATE_COHERENCE = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "validate_persona_coherence.py"
NORMALIZE_SCENARIO = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "product_scenario_normalizer.py"
RUN_CHOICE = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_choice_model.py"
VALIDATE_CHOICES = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "validate_choice_interviews.py"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DeterministicChoiceModelTest(unittest.TestCase):
    def test_enriched_personas_and_normalized_scenario_produce_valid_choice_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            seed_cells = tmp / "seed_cells.jsonl"
            weighted_cells = tmp / "weighted_cells.jsonl"
            margins = tmp / "margins.json"
            personas_core = tmp / "personas_core.jsonl"
            personas_enriched = tmp / "personas_enriched.jsonl"
            normalized_scenario = tmp / "normalized_choice_scenario.json"
            choice_results = tmp / "choice_results.jsonl"
            choice_audit = tmp / "choice_model_audit.json"
            validation_audit = tmp / "choice_validation.json"

            subprocess.run(
                [
                    sys.executable,
                    str(TO_CELLS),
                    str(COUNTRY_PACK),
                    "--dimension",
                    "region=Belgrade,Vojvodina",
                    "--dimension",
                    "sex=male,female",
                    "--dimension",
                    "education_level=secondary,tertiary",
                    "--dimension",
                    "income_decile=3,8",
                    "--dimension",
                    "settlement_type=urban,rural",
                    "--dimension",
                    "employment_status=employed,unemployed",
                    "--output",
                    str(seed_cells),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            margins.write_text(
                json.dumps(
                    {
                        "separator": "|",
                        "margins": [
                            {"name": "region", "variables": ["region"], "targets": {"Belgrade": 60.0, "Vojvodina": 40.0}},
                            {"name": "sex", "variables": ["sex"], "targets": {"male": 45.0, "female": 55.0}},
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            subprocess.run([sys.executable, str(RUN_IPF), str(seed_cells), str(margins), "--output", str(weighted_cells), "--iterations", "50", "--tolerance", "1e-9"], check=True, cwd=REPO_ROOT, capture_output=True, text=True)
            subprocess.run([sys.executable, str(SAMPLE_PERSONAS), str(weighted_cells), "--sample-size", "30", "--output", str(personas_core)], check=True, cwd=REPO_ROOT, capture_output=True, text=True)
            subprocess.run([sys.executable, str(EXPAND_SOFT), str(personas_core), "--category", "smartwatch", "--category-price-index", "0.7", "--output", str(personas_enriched)], check=True, cwd=REPO_ROOT, capture_output=True, text=True)
            subprocess.run([sys.executable, str(VALIDATE_COHERENCE), str(personas_enriched)], check=True, cwd=REPO_ROOT, capture_output=True, text=True)
            subprocess.run([sys.executable, str(NORMALIZE_SCENARIO), str(PRODUCT_SCENARIO), "--output", str(normalized_scenario)], check=True, cwd=REPO_ROOT, capture_output=True, text=True)
            subprocess.run([sys.executable, str(RUN_CHOICE), str(personas_enriched), str(normalized_scenario), "--output", str(choice_results), "--audit", str(choice_audit)], check=True, cwd=REPO_ROOT)

            validation = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_CHOICES),
                    str(choice_results),
                    "--audit",
                    str(validation_audit),
                    "--require-controls",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validation.returncode, 0, msg=validation.stdout + validation.stderr)

            rows = load_jsonl(choice_results)
            audit = json.loads(choice_audit.read_text(encoding="utf-8"))
            validation_summary = json.loads(validation_audit.read_text(encoding="utf-8"))

            self.assertEqual(len(rows), 30)
            self.assertEqual(audit["record_count"], 30)
            self.assertEqual(audit["method"], "deterministic_rule_based_random_utility_baseline")
            self.assertEqual(validation_summary["error_count"], 0)
            self.assertTrue(validation_summary["passes_choice_interview_integrity"])

            first = rows[0]
            for field in ("persona_id", "population_weight", "choice", "interview_response", "main_drivers", "main_barriers", "switch_conditions", "answer_confidence"):
                self.assertIn(field, first)
            self.assertIn(first["choice"], {"focal_product", "competitor", "none_or_delay"})
            self.assertIn("diagnostics", first)
            self.assertIn("utilities", first["diagnostics"])
            self.assertIn("isolation", first)
            self.assertFalse(first["isolation"]["saw_other_answers"])
            self.assertFalse(first["quality_controls"]["llm_generated"])


if __name__ == "__main__":
    unittest.main()
