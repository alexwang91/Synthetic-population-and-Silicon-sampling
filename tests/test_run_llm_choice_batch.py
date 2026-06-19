from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_llm_choice_interviews.py"
VALIDATOR = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "validate_choice_interviews.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_llm_choice_interviews", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load_module()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def export_prompts(tmp: Path, personas: list[dict], scenario: dict) -> Path:
    personas_path = tmp / "personas_enriched.jsonl"
    scenario_path = tmp / "scenario.json"
    prompts_path = tmp / "prompts.jsonl"
    write_jsonl(personas_path, personas)
    write_json(scenario_path, scenario)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "export-prompts", str(personas_path), str(scenario_path), "--output-prompts", str(prompts_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return prompts_path


SCENARIO = {
    "scenario_id": "demo",
    "category": "smartwatch",
    "currency": "EUR",
    "choice_task_type": "discrete_choice_cbc_style",
    "alternatives": [
        {"id": "A", "name": "Product A", "is_outside_option": False, "price": 100, "normalized_attributes": {"price_index": 0.0}},
        {"id": "B", "name": "Product B", "is_outside_option": False, "price": 120, "normalized_attributes": {"price_index": 1.0}},
        {"id": "none", "name": "None / delay", "is_outside_option": True, "price": None, "normalized_attributes": {}},
    ],
}

PERSONAS = [
    {"persona_id": f"RS-{index:03d}", "population_weight": 5.0 + index, "hard": {"sex": "female" if index % 2 else "male"}, "soft": {"psychographics": {"price_sensitivity": (index % 10) / 10.0}}}
    for index in range(1, 13)
]


class RunBatchMockTest(unittest.TestCase):
    def test_mock_batch_produces_valid_choice_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            prompts = export_prompts(tmp, PERSONAS, SCENARIO)
            choices = tmp / "choice_results.jsonl"
            audit = tmp / "batch_audit.json"
            cache = tmp / "cache"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "run-batch", str(prompts), "--provider", "mock", "--output", str(choices), "--audit", str(audit), "--concurrency", "4", "--cache-dir", str(cache)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            rows = read_jsonl(choices)
            self.assertEqual(len(rows), len(PERSONAS))
            for row in rows:
                self.assertIn(row["choice"], {"focal_product", "competitor", "none_or_delay"})
                self.assertEqual(row["generation_controls"]["method"], "llm_short_choice_interview")
                self.assertEqual(row["generation_controls"]["model"], "mock_deterministic_engine")
                self.assertTrue(row["generation_controls"]["seed"])
                self.assertTrue(row["quality_controls"]["llm_generated"])

            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            self.assertEqual(audit_data["provider"], "mock")
            self.assertEqual(audit_data["response_count"], len(PERSONAS))
            self.assertEqual(audit_data["failure_count"], 0)
            self.assertEqual(audit_data["coverage_rate"], 1.0)

            # Strict validation (the documented LLM-batch gate) must pass.
            validation = tmp / "validation.json"
            validate = subprocess.run(
                [sys.executable, str(VALIDATOR), str(choices), "--audit", str(validation), "--require-controls", "--strict"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.returncode, 0, msg=validate.stdout + validate.stderr)

    def test_cache_makes_reruns_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            prompts = export_prompts(tmp, PERSONAS, SCENARIO)
            cache = tmp / "cache"
            first = tmp / "first.jsonl"
            second = tmp / "second.jsonl"
            audit2 = tmp / "audit2.json"
            base = [sys.executable, str(SCRIPT), "run-batch", str(prompts), "--provider", "mock", "--cache-dir", str(cache)]
            run1 = subprocess.run(base + ["--output", str(first)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(run1.returncode, 0, msg=run1.stdout + run1.stderr)
            run2 = subprocess.run(base + ["--output", str(second), "--audit", str(audit2)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(run2.returncode, 0, msg=run2.stdout + run2.stderr)
            audit_data = json.loads(audit2.read_text(encoding="utf-8"))
            self.assertEqual(audit_data["cache_hits"], len(PERSONAS))
            # Deterministic mock + cache => byte-identical outputs across runs.
            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))

    def test_model_accepts_temperature_guard(self) -> None:
        # Opus 4.7/4.8 and Fable 5 reject sampling params; the runner must omit temperature.
        self.assertFalse(MOD.model_accepts_temperature("claude-opus-4-8"))
        self.assertFalse(MOD.model_accepts_temperature("claude-opus-4-7"))
        self.assertFalse(MOD.model_accepts_temperature("claude-fable-5"))
        self.assertTrue(MOD.model_accepts_temperature("claude-haiku-4-5"))
        self.assertTrue(MOD.model_accepts_temperature("claude-sonnet-4-6"))

    def test_extract_json_object_handles_fenced_and_prose(self) -> None:
        payload = {"choice": "focal_product", "answer_confidence": "high"}
        fenced = "```json\n" + json.dumps(payload) + "\n```"
        self.assertEqual(MOD.extract_json_object(fenced), payload)
        prose = "Sure, here is the answer: " + json.dumps(payload) + " — hope that helps."
        self.assertEqual(MOD.extract_json_object(prose), payload)
        with self.assertRaises(ValueError):
            MOD.extract_json_object("no json here at all")


if __name__ == "__main__":
    unittest.main()
