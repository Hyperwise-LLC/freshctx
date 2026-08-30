import json
import tempfile
import unittest
from pathlib import Path

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


class CompatibilityBaselineTests(unittest.TestCase):
    def test_stale_reasoning_blocks_and_never_emits_allow_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, audit = root / "source.json", root / "audit.jsonl"
            source.write_text('{"version": 1}\n')
            store = MemoryStore()
            with guard(store=store, audit_path=audit):
                token = observe(source)
                with reasoning("baseline", [token]) as node:
                    pass
            source.write_text('{"version": 2}\n')
            calls = []
            with self.assertRaises(FreshnessBlocked) as blocked:
                with guard(store=store, audit_path=audit) as ctx:
                    ctx.run(lambda: calls.append(True), depends_on=[node])
            self.assertEqual(blocked.exception.result.state.value, "STALE_REASONING")
            self.assertEqual(blocked.exception.result.policy_decision, "block")
            self.assertEqual(calls, [])
            events = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertFalse(any(event["event_type"] == "action_allowed" for event in events))


if __name__ == "__main__":
    unittest.main()
