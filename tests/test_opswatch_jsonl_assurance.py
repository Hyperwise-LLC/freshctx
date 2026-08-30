import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


EXAMPLE = Path(__file__).parents[1] / "examples" / "opswatch_jsonl_assurance.py"
SPEC = importlib.util.spec_from_file_location("opswatch_jsonl_assurance", EXAMPLE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OpsWatchJSONLAssuranceTests(unittest.TestCase):
    def run_case(self, behavior):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observed = MODULE.run_scenario(root, behavior)
            events = [
                json.loads(line)
                for line in (root / "freshctx-audit.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            saved = json.loads(
                (root / "downstream-observation.json").read_text(encoding="utf-8")
            )
            return observed, saved, events

    def test_respected_block_has_no_downstream_effect(self):
        observed, saved, events = self.run_case("respect")
        self.assertEqual(observed, saved)
        self.assertEqual(observed["freshctx_state"], "STALE_REASONING")
        self.assertEqual(observed["policy_decision"], "block")
        self.assertFalse(observed["effect_exists"])
        self.assertEqual(
            observed["assurance_verdict"], "PASS_AGENT_RESPECTED_BLOCK"
        )
        policy_events = [event for event in events if event["event_type"] == "policy_applied"]
        self.assertEqual(len(policy_events), 1)
        self.assertEqual(policy_events[0]["details"]["state"], "STALE_REASONING")
        self.assertEqual(policy_events[0]["details"]["policy_decision"], "block")
        self.assertFalse(
            any(event["event_type"] == "action_allowed" for event in events)
        )

    def test_bypassed_block_is_visible_to_independent_observer(self):
        observed, _saved, events = self.run_case("violate")
        self.assertTrue(observed["effect_exists"])
        self.assertEqual(
            observed["assurance_verdict"], "FAIL_AGENT_ACTED_AFTER_BLOCK"
        )
        self.assertTrue(
            any(
                event["event_type"] == "policy_applied"
                and event["details"]["policy_decision"] == "block"
                for event in events
            )
        )
        self.assertFalse(
            any(event["event_type"] == "action_allowed" for event in events)
        )


if __name__ == "__main__":
    unittest.main()
