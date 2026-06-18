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


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class PersonaSkeletonSamplerTest(unittest.TestCase):
    def test_weighted_cells_can_be_sampled_into_exact_persona_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            seed_cells = tmp / "seed_cells.jsonl"
            weighted_cells = tmp / "weighted_cells.jsonl"
            margins = tmp / "margins.json"
            personas_path = tmp / "personas_core.jsonl"
            audit_path = tmp / "persona_sampling_audit.json"
            ipf_audit = tmp / "ipf_audit.json"

            subprocess.run(
                [
                    sys.executable,
                    str(TO_CELLS),
                    str(COUNTRY_PACK),
                    "--dimension",
                    "region=Belgrade,Vojvodina",
                    "--dimension",
                    "sex=male,female",
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
                    "10",
                    "--output",
                    str(personas_path),
                    "--audit",
                    str(audit_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            personas = load_jsonl(personas_path)
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

            self.assertEqual(len(personas), 10)
            self.assertEqual(audit["requested_sample_size"], 10)
            self.assertEqual(audit["realized_sample_size"], 10)
            self.assertEqual(audit["allocation_method"], "largest_remainder")
            self.assertAlmostEqual(audit["total_cell_weight"], 100.0, places=6)
            self.assertAlmostEqual(audit["total_persona_weight"], 100.0, places=6)
            self.assertAlmostEqual(audit["absolute_total_weight_error"], 0.0, places=6)

            self.assertEqual(personas[0]["persona_id"], "RS-000001")
            self.assertIn("source_cell_id", personas[0])
            self.assertEqual(personas[0]["persona_stage"], "hard_statistical_skeleton")
            self.assertIsInstance(personas[0]["hard"], dict)
            self.assertIsInstance(personas[0]["soft"], dict)
            self.assertIn("persona_sampling", personas[0]["calibration_trace"])

            by_region: dict[str, float] = {"Belgrade": 0.0, "Vojvodina": 0.0}
            by_sex: dict[str, float] = {"male": 0.0, "female": 0.0}
            for persona in personas:
                by_region[persona["hard"]["region"]] += persona["population_weight"]
                by_sex[persona["hard"]["sex"]] += persona["population_weight"]

            self.assertAlmostEqual(by_region["Belgrade"], 60.0, places=6)
            self.assertAlmostEqual(by_region["Vojvodina"], 40.0, places=6)
            self.assertAlmostEqual(by_sex["male"], 45.0, places=6)
            self.assertAlmostEqual(by_sex["female"], 55.0, places=6)


if __name__ == "__main__":
    unittest.main()
