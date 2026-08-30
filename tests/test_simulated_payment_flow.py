import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


EXAMPLE = Path(__file__).parents[1] / "examples" / "simulated_payment_flow.py"
SPEC = importlib.util.spec_from_file_location("simulated_payment_flow", EXAMPLE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SimulatedPaymentFlowTests(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = MODULE.run_scenario(root, scenario)
            events = [json.loads(line) for line in Path(result["audit_path"]).read_text().splitlines()]
            return result, events

    def test_current_and_unrelated_change_allow(self):
        for scenario in ("current", "unrelated_changed"):
            result, events = self.run_case(scenario)
            self.assertEqual(result["state"], "CURRENT")
            self.assertEqual(result["policy_decision"], "allow")
            self.assertTrue(result["simulated_action_executed"])
            self.assertTrue(any(event["event_type"] == "action_allowed" for event in events))

    def test_declared_balance_and_approval_changes_block_without_allow_evidence(self):
        for scenario in ("balance_changed", "approval_changed"):
            result, events = self.run_case(scenario)
            self.assertEqual(result["state"], "STALE_REASONING")
            self.assertEqual(result["policy_decision"], "block")
            self.assertFalse(result["simulated_action_executed"])
            self.assertFalse(any(event["event_type"] == "action_allowed" for event in events))
            self.assertTrue(any(
                event["event_type"] == "policy_applied"
                and event["details"]["state"] == "STALE_REASONING"
                and event["details"]["policy_decision"] == "block"
                for event in events
            ))


if __name__ == "__main__":
    unittest.main()
