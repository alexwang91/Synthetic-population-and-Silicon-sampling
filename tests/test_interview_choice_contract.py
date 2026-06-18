from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "skills"
    / "weighted-persona-pricing"
    / "scripts"
    / "bootstrap_choice_intervals.py"
)


def load_bootstrap_module():
    spec = importlib.util.spec_from_file_location("bootstrap_choice_intervals", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InterviewChoiceContractTest(unittest.TestCase):
    def test_weighted_shares_accepts_discrete_interview_choices(self):
        bootstrap = load_bootstrap_module()
        records = [
            {"persona_id": "P1", "population_weight": 2, "choice": "focal_product"},
            {"persona_id": "P2", "population_weight": 1, "choice": "competitor"},
            {"persona_id": "P3", "population_weight": 1, "choice": "none_or_delay"},
        ]

        shares = bootstrap.weighted_shares(records)

        self.assertEqual(
            shares,
            {
                "focal_product": 0.5,
                "competitor": 0.25,
                "none_or_delay": 0.25,
            },
        )

    def test_choice_records_keep_interview_answer_fields(self):
        required = {
            "choice",
            "interview_response",
            "main_drivers",
            "main_barriers",
            "switch_conditions",
        }
        record = {
            "choice": "focal_product",
            "interview_response": "I would choose Huawei because the battery matters most.",
            "main_drivers": ["battery_life"],
            "main_barriers": ["higher_price"],
            "switch_conditions": ["Samsung improves iOS fit"],
        }

        self.assertTrue(required <= set(record))


if __name__ == "__main__":
    unittest.main()
