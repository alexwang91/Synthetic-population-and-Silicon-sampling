from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_llm_batch_audit.py"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ValidateLlmBatchAuditTest(unittest.TestCase):
    def test_batch_audit_passes_when_failure_and_coverage_are_within_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit = Path(tmpdir) / "audit.json"
            write_json(audit, {"prompt_count": 200, "response_count": 200, "failure_count": 1, "coverage_rate": 1.0})
            result = subprocess.run([sys.executable, str(SCRIPT), str(audit), "--max-failure-rate", "0.005"], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            output = json.loads(result.stdout)
            self.assertTrue(output["passes_llm_batch_gate"])

    def test_batch_audit_fails_when_failure_rate_exceeds_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit = Path(tmpdir) / "audit.json"
            write_json(audit, {"prompt_count": 100, "response_count": 100, "failure_count": 1, "coverage_rate": 1.0})
            result = subprocess.run([sys.executable, str(SCRIPT), str(audit), "--max-failure-rate", "0.005"], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertFalse(output["passes_llm_batch_gate"])
            self.assertEqual(output["issues"][0]["issue"], "failure_rate_exceeds_threshold")

    def test_batch_audit_fails_when_coverage_rate_is_too_low(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit = Path(tmpdir) / "audit.json"
            write_json(audit, {"prompt_count": 1000, "response_count": 990, "failure_count": 0, "coverage_rate": 0.99})
            result = subprocess.run([sys.executable, str(SCRIPT), str(audit), "--min-coverage-rate", "0.995"], cwd=REPO_ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertFalse(output["passes_llm_batch_gate"])
            self.assertEqual(output["issues"][0]["issue"], "coverage_rate_below_threshold")


if __name__ == "__main__":
    unittest.main()
