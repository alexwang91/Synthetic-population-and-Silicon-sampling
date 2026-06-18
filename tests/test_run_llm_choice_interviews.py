from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_llm_choice_interviews.py"
VALIDATOR = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "validate_choice_interviews.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class LLMChoiceInterviewTest(unittest.TestCase):
    def test_export_prompts_for_each_persona(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            personas = tmp / "personas_enriched.jsonl"
            scenario = tmp / "scenario.json"
            prompts = tmp / "llm_prompts.jsonl"
            audit = tmp / "audit.json"
            write_jsonl(
                personas,
                [
                    {"persona_id": "RS-001", "population_weight": 10.0, "hard": {"sex": "female"}, "soft": {"psychographics": {"price_sensitivity": 0.5}}},
                    {"persona_id": "RS-002", "population_weight": 20.0, "hard": {"sex": "male"}, "soft": {"psychographics": {"price_sensitivity": 0.7}}},
                ],
            )
            write_json(
                scenario,
                {
                    "scenario_id": "demo",
                    "category": "smartwatch",
                    "currency": "EUR",
                    "choice_task_type": "discrete_choice_cbc_style",
                    "alternatives": [
                        {"id": "A", "name": "Product A", "is_outside_option": False, "price": 100, "normalized_attributes": {"price_index": 0.0}},
                        {"id": "B", "name": "Product B", "is_outside_option": False, "price": 120, "normalized_attributes": {"price_index": 1.0}},
                        {"id": "none", "name": "None / delay", "is_outside_option": True, "price": None, "normalized_attributes": {}},
                    ],
                },
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "export-prompts", str(personas), str(scenario), "--output-prompts", str(prompts), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            rows = read_jsonl(prompts)
            self.assertEqual(len(rows), 2)
            self.assertIn("Allowed choice values", rows[0]["prompt"])
            self.assertEqual(rows[0]["prompt_version"], "llm_choice_short_v0_1")
            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            self.assertEqual(audit_data["prompt_count"], 2)

    def test_normalize_external_responses_to_choice_results_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            prompts = tmp / "prompts.jsonl"
            responses = tmp / "responses.jsonl"
            choices = tmp / "choice_results.jsonl"
            audit = tmp / "audit.json"
            validation = tmp / "validation.json"
            write_jsonl(
                prompts,
                [
                    {"task_id": "task1", "persona_id": "RS-001", "population_weight": 10.0},
                    {"task_id": "task2", "persona_id": "RS-002", "population_weight": 20.0},
                ],
            )
            write_jsonl(
                responses,
                [
                    {
                        "task_id": "task1",
                        "persona_id": "RS-001",
                        "choice": "focal_product",
                        "chosen_alternative_id": "A",
                        "chosen_alternative_name": "Product A",
                        "interview_response": "I would choose Product A because it fits my budget better.",
                        "main_drivers": ["price_fit"],
                        "main_barriers": ["brand_uncertainty"],
                        "switch_conditions": ["if Product B were cheaper"],
                        "answer_confidence": "medium",
                        "model": "external-test-model",
                        "temperature": 0.4,
                    },
                    {
                        "task_id": "task2",
                        "persona_id": "RS-002",
                        "choice": "competitor",
                        "chosen_alternative_id": "B",
                        "chosen_alternative_name": "Product B",
                        "interview_response": "I would choose Product B because the brand feels safer.",
                        "main_drivers": ["brand_trust"],
                        "main_barriers": ["higher_price"],
                        "switch_conditions": ["better warranty for Product A"],
                        "answer_confidence": "high",
                    },
                ],
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "normalize-responses", str(prompts), str(responses), "--output", str(choices), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            validate = subprocess.run(
                [sys.executable, str(VALIDATOR), str(choices), "--audit", str(validation), "--require-controls"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.returncode, 0, msg=validate.stdout + validate.stderr)
            rows = read_jsonl(choices)
            self.assertEqual(len(rows), 2)
            self.assertTrue(rows[0]["quality_controls"]["llm_generated"])
            self.assertEqual(rows[0]["generation_controls"]["method"], "llm_short_choice_interview")
            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            self.assertEqual(audit_data["coverage_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
