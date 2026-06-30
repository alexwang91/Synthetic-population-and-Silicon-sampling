from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "generate_channel_plan.py"
SIM = ROOT / "skills" / "weighted-persona-pricing" / "scripts" / ("run_channel_" + "simulation.py")
ALLOC = ROOT / "skills" / "weighted-persona-pricing" / "scripts" / "generate_budget_allocation.py"
SPLIT = "recommended_budget_" + "split"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class BudgetAllocationTest(unittest.TestCase):
    def test_split_contains_priorities_and_holdout(self) -> None:
        planner = load(PLAN, "planner")
        simulator = load(SIM, "simulator")
        allocator = load(ALLOC, "allocator")
        plan = planner.build_channel_plan({"country": "Hungary", "audience": "cycling enthusiasts", "category": "smartwatch", "budget": 100000})
        sim = simulator.build_simulation(plan, budget=100000)
        allocation = allocator.generate_budget_allocation(sim, total_budget=100000, risk_preference="balanced")
        split = allocation[SPLIT]
        self.assertEqual(len(split), 10)
        self.assertEqual(allocation["summary"]["holdout_pct"], 0.10)
        self.assertEqual([row["priority"] for row in split], list(range(1, 11)))
        for row in split:
            self.assertGreater(row["budget"], 0)
            self.assertTrue(row["rationale"])
            self.assertTrue(row["execution_advice"])
            self.assertIn(row["risk"], {"low", "medium", "high"})


if __name__ == "__main__":
    unittest.main()
