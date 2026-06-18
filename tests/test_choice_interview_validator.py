from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "skills"
    / "weighted-persona-pricing"
    / "scripts"
    / "validate_choice_interviews.py"
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class ChoiceInterviewValidatorTest(unittest.TestCase):
    def run_validator(self, rows: list[dict], *flags: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "choice_results.jsonl"
            write_jsonl(path, rows)
            return subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(path), *flags],
                text=True,
                capture_output=True,
                check=False,
            )

    def test_accepts_isolated_interview_record_with_controls(self):
        result = self.run_validator(
            [
                {
                    "persona_id": "P1",
                    "population_weight": 10,
                    "choice": "focal_product",
                    "interview_response": "I would choose Huawei because battery life matters.",
                    "main_drivers": ["battery_life"],
                    "main_barriers": ["higher_price"],
                    "switch_conditions": ["Samsung improves battery"],
                    "answer_confidence": "medium",
                    "isolation": {
                        "context_scope": "individual",
                        "saw_other_answers": False,
                        "saw_aggregate_results": False,
                    },
                    "generation_controls": {
                        "seed": "scenario:P1",
                        "temperature": 0.2,
                        "prompt_variant": "base",
                    },
                    "quality_controls": {
                        "consistency_judge": "pass",
                        "test_retest_status": "not_sampled",
                        "prompt_sensitivity_status": "not_sampled",
                    },
                }
            ],
            "--require-controls",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_rejects_probability_only_rows(self):
        result = self.run_validator(
            [
                {
                    "persona_id": "P1",
                    "population_weight": 10,
                    "choice_probability": {"focal_product": 0.7, "competitor": 0.3},
                }
            ]
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_required", result.stdout)

    def test_rejects_context_contamination_when_strict(self):
        result = self.run_validator(
            [
                {
                    "persona_id": "P1",
                    "population_weight": 10,
                    "choice": "competitor",
                    "interview_response": "I saw the aggregate share and other respondents, so I choose Samsung.",
                    "main_drivers": ["lower_price"],
                    "main_barriers": ["higher_price"],
                    "switch_conditions": ["Huawei discount"],
                    "answer_confidence": "high",
                    "isolation": {
                        "context_scope": "batch",
                        "saw_other_answers": True,
                        "saw_aggregate_results": True,
                    },
                    "generation_controls": {
                        "seed": "scenario:P1",
                        "temperature": 0.2,
                        "prompt_variant": "base",
                    },
                    "quality_controls": {
                        "consistency_judge": "pass",
                    },
                }
            ],
            "--strict",
            "--require-controls",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contamination", result.stdout)


if __name__ == "__main__":
    unittest.main()
