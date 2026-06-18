from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "validate_llm_choice_quality.py"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_personas() -> list[dict]:
    rows = []
    for i in range(1, 25):
        rows.append(
            {
                "persona_id": f"P-{i:03d}",
                "population_weight": 1.0,
                "hard": {
                    "region": "North" if i <= 12 else "South",
                    "sex": "female" if i % 2 == 0 else "male",
                    "income_decile": "8" if i % 3 == 0 else "3",
                },
                "soft": {},
            }
        )
    return rows


def make_choice_row(persona_id: str, choice: str, chosen_id: str, position_order: list[str]) -> dict:
    return {
        "persona_id": persona_id,
        "population_weight": 1.0,
        "choice": choice,
        "chosen_alternative_id": chosen_id,
        "chosen_alternative_name": chosen_id,
        "interview_response": "Synthetic short response.",
        "main_drivers": [f"driver_{choice}", "price_fit"],
        "main_barriers": ["barrier", f"barrier_{choice}"],
        "switch_conditions": ["if price changed"],
        "answer_confidence": "high" if choice == "focal_product" else "medium",
        "generation_controls": {
            "method": "llm_short_choice_interview",
            "prompt_version": "llm_choice_short_v0_2",
            "prompt_variant": "tradeoff",
            "order_policy": "rotate",
            "presented_alternative_order": position_order,
            "choice_label_map": {"A": "focal_product", "B": "competitor", "none": "none_or_delay"},
        },
        "quality_controls": {"llm_generated": True, "score_only": False, "discrete_choice_record": True},
        "isolation": {"saw_other_answers": False, "saw_aggregate_results": False, "saw_target_proportion": False},
    }


class LLMChoiceQualityValidatorTest(unittest.TestCase):
    def test_balanced_varied_llm_choices_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            personas = tmp / "personas.jsonl"
            choices = tmp / "choices.jsonl"
            audit = tmp / "audit.json"
            persona_rows = make_personas()
            write_jsonl(personas, persona_rows)
            choice_rows = []
            for i, persona in enumerate(persona_rows):
                if i % 3 == 0:
                    choice_rows.append(make_choice_row(persona["persona_id"], "focal_product", "A", ["A", "B", "none"]))
                elif i % 3 == 1:
                    choice_rows.append(make_choice_row(persona["persona_id"], "competitor", "B", ["B", "A", "none"]))
                else:
                    choice_rows.append(make_choice_row(persona["persona_id"], "none_or_delay", "none", ["A", "none", "B"]))
            write_jsonl(choices, choice_rows)
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    str(personas),
                    str(choices),
                    "--audit",
                    str(audit),
                    "--min-meaningful-delta",
                    "0.9",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = load_json(audit)
            self.assertTrue(summary["passes_llm_choice_quality_validation"])
            self.assertEqual(summary["error_count"], 0)
            self.assertIn("choice_distribution", summary)
            self.assertGreaterEqual(summary["choice_distribution"]["normalized_entropy"], 0.9)

    def test_single_choice_collapse_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            personas = tmp / "personas.jsonl"
            choices = tmp / "choices.jsonl"
            audit = tmp / "audit.json"
            persona_rows = make_personas()
            write_jsonl(personas, persona_rows)
            write_jsonl(choices, [make_choice_row(row["persona_id"], "focal_product", "A", ["A", "B", "none"]) for row in persona_rows])
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(personas), str(choices), "--audit", str(audit)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            summary = load_json(audit)
            issues = {item["issue"] for item in summary["errors"]}
            self.assertIn("choice_collapse_single_option", issues)

    def test_position_bias_warning_does_not_fail_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            personas = tmp / "personas.jsonl"
            choices = tmp / "choices.jsonl"
            audit = tmp / "audit.json"
            persona_rows = make_personas()
            write_jsonl(personas, persona_rows)
            choice_rows = []
            for i, persona in enumerate(persona_rows):
                if i % 2 == 0:
                    choice_rows.append(make_choice_row(persona["persona_id"], "focal_product", "A", ["A", "B", "none"]))
                else:
                    choice_rows.append(make_choice_row(persona["persona_id"], "competitor", "B", ["B", "A", "none"]))
            write_jsonl(choices, choice_rows)
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(personas), str(choices), "--audit", str(audit), "--max-position-share", "0.6"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            summary = load_json(audit)
            issues = {item["issue"] for item in summary["warnings"]}
            self.assertIn("possible_position_or_order_bias", issues)


if __name__ == "__main__":
    unittest.main()
