from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "run_llm_choice_interviews_contract.py"
VALIDATOR = REPO_ROOT / "scripts" / "validate_jsonl_schema.py"
SCHEMA = REPO_ROOT / "schemas" / "choice_results.schema.json"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
    {"persona_id": f"RS-{index:03d}", "population_weight": 5.0 + index, "hard": {}, "soft": {"psychographics": {"price_sensitivity": 0.3}}}
    for index in range(1, 4)
]


def export_prompts(tmp: Path) -> Path:
    personas = tmp / "personas_enriched.jsonl"
    scenario = tmp / "scenario.json"
    prompts = tmp / "prompts.jsonl"
    audit = tmp / "prompt_audit.json"
    write_jsonl(personas, PERSONAS)
    write_json(scenario, SCENARIO)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "export-prompts", str(personas), str(scenario), "--output-prompts", str(prompts), "--audit", str(audit)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    assert audit_data["prompt_hash_count"] == len(PERSONAS)
    return prompts


class LLMChoiceCacheContractTest(unittest.TestCase):
    def test_prompt_export_records_prompt_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts = export_prompts(Path(tmpdir))
            rows = read_jsonl(prompts)
            self.assertEqual(len(rows), len(PERSONAS))
            for row in rows:
                self.assertRegex(row["prompt_hash"], r"^[a-f0-9]{64}$")

    def test_mock_batch_cache_is_bound_to_model_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            prompts = export_prompts(tmp)
            cache = tmp / "cache"
            first = tmp / "first.jsonl"
            second = tmp / "second.jsonl"
            third = tmp / "third.jsonl"
            audit1 = tmp / "audit1.json"
            audit2 = tmp / "audit2.json"
            audit3 = tmp / "audit3.json"
            base = [sys.executable, str(SCRIPT), "run-batch", str(prompts), "--provider", "mock", "--cache-dir", str(cache)]

            run1 = subprocess.run(base + ["--model", "mock-model-a", "--output", str(first), "--audit", str(audit1)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(run1.returncode, 0, msg=run1.stdout + run1.stderr)
            run2 = subprocess.run(base + ["--model", "mock-model-a", "--output", str(second), "--audit", str(audit2)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(run2.returncode, 0, msg=run2.stdout + run2.stderr)
            run3 = subprocess.run(base + ["--model", "mock-model-b", "--output", str(third), "--audit", str(audit3)], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(run3.returncode, 0, msg=run3.stdout + run3.stderr)

            audit_data1 = json.loads(audit1.read_text(encoding="utf-8"))
            audit_data2 = json.loads(audit2.read_text(encoding="utf-8"))
            audit_data3 = json.loads(audit3.read_text(encoding="utf-8"))
            self.assertEqual(audit_data1["cache_hits"], 0)
            self.assertEqual(audit_data2["cache_hits"], len(PERSONAS))
            self.assertEqual(audit_data3["cache_hits"], 0)
            self.assertNotEqual(audit_data2["cache_namespace_key"], audit_data3["cache_namespace_key"])
            self.assertEqual(audit_data2["cache_contract"]["version"], "llm_choice_cache_v0_2")

            rows = read_jsonl(second)
            for row in rows:
                self.assertRegex(row["generation_controls"]["prompt_hash"], r"^[a-f0-9]{64}$")
                self.assertRegex(row["generation_controls"]["cache_key"], r"^[a-f0-9]{32}$")

            validation = tmp / "schema_audit.json"
            validate = subprocess.run(
                [sys.executable, str(VALIDATOR), str(SCHEMA), str(second), "--audit", str(validation)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.returncode, 0, msg=validate.stdout + validate.stderr)


if __name__ == "__main__":
    unittest.main()
