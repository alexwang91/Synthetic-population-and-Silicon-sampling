from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_scenario_pipeline.py"
CONFIG = REPO_ROOT / "skills" / "weighted-persona-pricing" / "examples" / "serbia_smartwatch_pipeline_config.json"


class ScenarioPipelineRunnerTest(unittest.TestCase):
    def test_pipeline_config_produces_manifest_and_core_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run(
                [sys.executable, str(PIPELINE), str(CONFIG), "--output-root", str(output_root)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

            run_dir = output_root / "serbia_smartwatch_pipeline_demo"
            manifest_path = run_dir / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["method"], "deterministic_reproducible_scenario_pipeline")
            self.assertFalse(manifest["scientific_boundary"]["pipeline_changes_model_outputs"])
            step_names = [step["step"] for step in manifest["steps"]]
            self.assertEqual(
                step_names,
                [
                    "validate_country_pack",
                    "country_pack_to_cells",
                    "run_ipf",
                    "sample_persona_skeletons",
                    "expand_soft_traits",
                    "validate_persona_coherence",
                    "product_scenario_normalizer",
                    "run_choice_model",
                    "validate_choice_interviews",
                    "bootstrap_choice_intervals",
                ],
            )
            self.assertTrue((run_dir / "choice_results.jsonl").exists())
            self.assertTrue((run_dir / "choice_model_audit.json").exists())
            self.assertTrue((run_dir / "choice_interview_validation.json").exists())
            self.assertTrue((run_dir / "bootstrap_intervals.json").exists())

            choice_validation = json.loads((run_dir / "choice_interview_validation.json").read_text(encoding="utf-8"))
            self.assertTrue(choice_validation["passes_choice_interview_integrity"])
            self.assertEqual(choice_validation["record_count"], 40)

    def test_pipeline_can_stop_after_intermediate_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "runs"
            result = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE),
                    str(CONFIG),
                    "--output-root",
                    str(output_root),
                    "--stop-after",
                    "expand_soft_traits",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

            run_dir = output_root / "serbia_smartwatch_pipeline_demo"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "stopped")
            self.assertTrue((run_dir / "personas_enriched.jsonl").exists())
            self.assertFalse((run_dir / "choice_results.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
