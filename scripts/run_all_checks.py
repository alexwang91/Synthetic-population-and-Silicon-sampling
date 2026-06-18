#!/usr/bin/env python3
"""Run lightweight repository checks.

This runner is intended for local smoke checks and future CI wiring. It keeps
checks explicit and avoids loading large row-level artifacts into memory except
inside the targeted tests that need them.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


REPO_ROOT = Path(__file__).resolve().parents[1]


class Check(NamedTuple):
    name: str
    command: list[str]
    slow: bool = False


FAST_CHECKS = [
    Check("country_pack_builder", [sys.executable, "tests/test_country_pack_builder.py"]),
    Check("country_pack_ipf_pipeline", [sys.executable, "tests/test_country_pack_ipf_pipeline.py"]),
    Check("persona_skeleton_sampler", [sys.executable, "tests/test_sample_persona_skeletons.py"]),
    Check("soft_trait_expansion", [sys.executable, "tests/test_expand_soft_traits.py"]),
    Check("persona_coherence", [sys.executable, "tests/test_validate_persona_coherence.py"]),
    Check("product_scenario_normalizer", [sys.executable, "tests/test_product_scenario_normalizer.py"]),
    Check("choice_model", [sys.executable, "tests/test_run_choice_model.py"]),
    Check("llm_choice_interviews", [sys.executable, "tests/test_run_llm_choice_interviews.py"]),
    Check("llm_choice_quality", [sys.executable, "tests/test_validate_llm_choice_quality.py"]),
    Check("pipeline_artifact_validator", [sys.executable, "tests/test_validate_pipeline_artifacts.py"]),
    Check("choice_interview_validator", [sys.executable, "tests/test_choice_interview_validator.py"]),
    Check("interview_choice_contract", [sys.executable, "tests/test_interview_choice_contract.py"]),
]

SLOW_CHECKS = [
    Check("scenario_pipeline_smoke", [sys.executable, "tests/test_run_scenario_pipeline.py"], slow=True),
]


def run_check(check: Check) -> dict[str, object]:
    process = subprocess.run(check.command, cwd=REPO_ROOT, capture_output=True, text=True)
    return {
        "name": check.name,
        "command": " ".join(check.command),
        "returncode": process.returncode,
        "status": "passed" if process.returncode == 0 else "failed",
        "stdout_tail": process.stdout[-2000:],
        "stderr_tail": process.stderr[-2000:],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-slow", action="store_true", help="Include the end-to-end scenario pipeline smoke test.")
    parser.add_argument("--only", choices=[check.name for check in FAST_CHECKS + SLOW_CHECKS])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = list(FAST_CHECKS)
    if args.include_slow:
        checks.extend(SLOW_CHECKS)
    if args.only:
        checks = [check for check in FAST_CHECKS + SLOW_CHECKS if check.name == args.only]

    failed = []
    for check in checks:
        result = run_check(check)
        print(f"[{result['status']}] {result['name']} :: {result['command']}")
        if result["returncode"] != 0:
            failed.append(result)
            if result["stdout_tail"]:
                print("--- stdout tail ---")
                print(result["stdout_tail"])
            if result["stderr_tail"]:
                print("--- stderr tail ---")
                print(result["stderr_tail"])

    if failed:
        print(f"\n{len(failed)} check(s) failed.")
        return 1
    print(f"\n{len(checks)} check(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
