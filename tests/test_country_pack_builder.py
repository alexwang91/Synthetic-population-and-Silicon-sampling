from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "build_country_pack.py"
VALIDATOR = REPO_ROOT / "skills" / "country-pack-builder" / "scripts" / "validate_country_pack.py"
SERBIA_EXAMPLE = REPO_ROOT / "skills" / "country-pack-builder" / "examples" / "RS_country_pack_v0_1.json"


class CountryPackBuilderTest(unittest.TestCase):
    def test_builder_creates_valid_anchor_ready_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "RS_country_pack.json"
            subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--country-name",
                    "Serbia",
                    "--iso2",
                    "RS",
                    "--iso3",
                    "SRB",
                    "--population-year",
                    "2022",
                    "--nso-name",
                    "Statistical Office of the Republic of Serbia",
                    "--nso-url",
                    "https://www.stat.gov.rs/",
                    "--total-population",
                    "6647003",
                    "--male-count",
                    "3231978",
                    "--female-count",
                    "3415025",
                    "--output",
                    str(output),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            pack = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(pack["country_identity"]["iso2"], "RS")
            self.assertEqual(pack["build_status"]["status"], "anchor_ready")
            self.assertFalse(pack["build_status"]["can_claim_census_calibrated_panel"])
            self.assertIn("population_total", pack["extracted_anchor_values"])
            self.assertIn("sex_distribution", pack["extracted_anchor_values"])

            validation = subprocess.run(
                [sys.executable, str(VALIDATOR), str(output)],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            summary = json.loads(validation.stdout)
            self.assertTrue(summary["passes_country_pack_integrity"])
            self.assertEqual(summary["build_status"], "anchor_ready")

    def test_serbia_example_passes_country_pack_validator(self) -> None:
        validation = subprocess.run(
            [sys.executable, str(VALIDATOR), str(SERBIA_EXAMPLE)],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        summary = json.loads(validation.stdout)
        self.assertTrue(summary["passes_country_pack_integrity"])
        self.assertEqual(summary["iso2"], "RS")


if __name__ == "__main__":
    unittest.main()
