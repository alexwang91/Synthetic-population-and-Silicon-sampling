from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_jsonl_schema.py"
SCHEMA = REPO_ROOT / "schemas" / "choice_results.schema.json"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


VALID_ROW = {
    "persona_id": "RS-000001",
    "population_weight": 123.4,
    "choice": "focal_product",
    "chosen_alternative_id": "A",
    "chosen_alternative_name": "Product A",
    "interview_response": "I would choose Product A.",
    "main_drivers": ["brand_fit"],
    "main_barriers": ["price_fit"],
    "switch_conditions": ["lower price"],
    "answer_confidence": "medium",
    "isolation": {
        "context_scope": "single_persona",
        "saw_other_answers": False,
        "saw_aggregate_results": False,
        "saw_target_proportion": False,
    },
    "generation_controls": {
        "method": "llm_short_choice_interview",
        "model": "mock_deterministic_engine",
        "seed": "task:abc",
        "temperature": None,
    },
    "quality_controls": {
        "llm_generated": True,
        "score_only": False,
        "discrete_choice_record": True,
        "probabilities_are_diagnostics_only": False,
        "calibration_level": "mock_offline_uncalibrated",
    },
}


class ChoiceResultsSchemaTest(unittest.TestCase):
    def test_valid_choice_result_row_passes_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "choice_results.jsonl"
            write_jsonl(path, [VALID_ROW])
            result = subprocess.run([sys.executable, str(VALIDATOR), str(SCHEMA), str(path)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            audit = json.loads(result.stdout)
            self.assertTrue(audit["passes_schema_validation"])
            self.assertEqual(audit["record_count"], 1)

    def test_invalid_choice_result_row_fails_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "choice_results.jsonl"
            invalid = dict(VALID_ROW)
            invalid["choice"] = "Product A"
            write_jsonl(path, [invalid])
            result = subprocess.run([sys.executable, str(VALIDATOR), str(SCHEMA), str(path)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            audit = json.loads(result.stdout)
            self.assertFalse(audit["passes_schema_validation"])
            self.assertGreater(audit["error_count"], 0)


if __name__ == "__main__":
    unittest.main()
