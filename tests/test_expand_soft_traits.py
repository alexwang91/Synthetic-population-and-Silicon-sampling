from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COUNTRY_PACK = REPO_ROOT / "skills" / "country-pack-builder" / "examples" / "RS_country_pack_v0_1.json"
TO_CELLS = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "country_pack_to_cells.py"
RUN_IPF = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "run_ipf.py"
SAMPLE_PERSONAS = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "sample_persona_skeletons.py"
EXPAND_SOFT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "expand_soft_traits.py"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class SoftTraitExpansionTest(unittest.TestCase):
    def test_persona_skeletons_can_be_enriched_with_soft_traits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            seed_cells = tmp / "seed_cells.jsonl"
            weighted_cells = tmp / "weighted_cells.jsonl"
            margins = tmp / "margins.json"
            personas_core = tmp / "personas_core.jsonl"
            personas_enriched = tmp / "personas_enriched.jsonl"
            ipf_audit = tmp / "ipf_audit.json"
            sampling_audit = tmp / "persona_sampling_audit.json"
            soft_audit = tmp / "soft_trait_audit.json"

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
                            {
                                "name": "region",
                                "variables": ["region"],
                                "targets": {"Belgrade": 60.0, "Vojvodina": 40.0},
                            },
                            {
                                "name": "sex",
                                "variables": ["sex"],
                                "targets": {"male": 45.0, "female": 55.0},
                            },
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(RUN_IPF),
                    str(seed_cells),
                    str(margins),
                    "--output",
                    str(weighted_cells),
                    "--audit",
                    str(ipf_audit),
                    "--iterations",
                    "50",
                    "--tolerance",
                    "1e-9",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SAMPLE_PERSONAS),
                    str(weighted_cells),
                    "--sample-size",
                    "20",
                    "--output",
                    str(personas_core),
                    "--audit",
                    str(sampling_audit),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            subprocess.run(
                [
                    sys.executable,
                    str(EXPAND_SOFT),
                    str(personas_core),
                    "--category",
                    "smartwatch",
                    "--category-price-index",
                    "0.7",
                    "--output",
                    str(personas_enriched),
                    "--audit",
                    str(soft_audit),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            enriched = load_jsonl(personas_enriched)
            audit = json.loads(soft_audit.read_text(encoding="utf-8"))

            self.assertEqual(len(enriched), 20)
            self.assertEqual(audit["record_count"], 20)
            self.assertEqual(audit["category"], "smartwatch")
            self.assertFalse(audit["llm_generated"])
            self.assertIn("price_sensitivity", audit["mean_scores"])

            first = enriched[0]
            self.assertEqual(first["persona_stage"], "soft_trait_enriched_skeleton")
            self.assertIn("media_habits", first["soft"])
            self.assertIn("shopping_habits", first["soft"])
            self.assertIn("psychographics", first["soft"])
            self.assertIn("category_priors", first["soft"])
            self.assertIn("soft_trait_trace", first["soft"])
            self.assertFalse(first["soft"]["soft_trait_trace"]["llm_generated"])
            self.assertEqual(first["soft"]["category_priors"]["category"], "smartwatch")
            self.assertIn("soft_trait_expansion", first["calibration_trace"])

            for record in enriched:
                psych = record["soft"]["psychographics"]
                for key in ("price_sensitivity", "risk_aversion", "budget_pressure", "review_dependency"):
                    self.assertGreaterEqual(psych[key], 0.0)
                    self.assertLessEqual(psych[key], 1.0)

    def test_soft_trait_expansion_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            personas_core = tmp / "personas_core.jsonl"
            out_a = tmp / "out_a.jsonl"
            out_b = tmp / "out_b.jsonl"

            personas_core.write_text(
                json.dumps(
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
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            for output in (out_a, out_b):
                subprocess.run(
                    [
                        sys.executable,
                        str(EXPAND_SOFT),
                        str(personas_core),
                        "--category",
                        "appliance",
                        "--category-price-index",
                        "0.5",
                        "--output",
                        str(output),
                    ],
                    check=True,
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(out_a.read_text(encoding="utf-8"), out_b.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
