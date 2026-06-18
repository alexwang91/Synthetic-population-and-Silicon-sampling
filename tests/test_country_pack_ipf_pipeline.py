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


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class CountryPackIpfPipelineTest(unittest.TestCase):
    def test_seed_cells_can_be_raked_to_region_and_sex_margins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            seed_cells = tmp / "seed_cells.jsonl"
            weighted_cells = tmp / "weighted_cells.jsonl"
            margins = tmp / "margins.json"
            audit = tmp / "ipf_audit.json"

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

            seed = load_jsonl(seed_cells)
            self.assertEqual(len(seed), 4)
            self.assertEqual({row["hard"]["region"] for row in seed}, {"Belgrade", "Vojvodina"})
            self.assertEqual({row["hard"]["sex"] for row in seed}, {"male", "female"})

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
                    str(audit),
                    "--iterations",
                    "50",
                    "--tolerance",
                    "1e-9",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            weighted = load_jsonl(weighted_cells)
            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            self.assertTrue(audit_data["converged"])
            self.assertAlmostEqual(audit_data["total_weight"], 100.0, places=6)
            self.assertTrue(all(row["ipf_ready"] is True for row in weighted))

            by_region: dict[str, float] = {"Belgrade": 0.0, "Vojvodina": 0.0}
            by_sex: dict[str, float] = {"male": 0.0, "female": 0.0}
            for row in weighted:
                by_region[row["hard"]["region"]] += row["population_weight"]
                by_sex[row["hard"]["sex"]] += row["population_weight"]

            self.assertAlmostEqual(by_region["Belgrade"], 60.0, places=6)
            self.assertAlmostEqual(by_region["Vojvodina"], 40.0, places=6)
            self.assertAlmostEqual(by_sex["male"], 45.0, places=6)
            self.assertAlmostEqual(by_sex["female"], 55.0, places=6)


if __name__ == "__main__":
    unittest.main()
