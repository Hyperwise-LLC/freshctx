import hashlib
import tempfile
import unittest
from pathlib import Path

from freshctx import FreshnessStatus, MemoryStore, ObservationToken, guard, observe, reasoning, register_adapter
from freshctx.model import AdapterResult


class _ExternalAdapter:
    name = "external-test"

    def __init__(self, state):
        self.state = state

    def observe(self, locator, **_options):
        return ObservationToken(self.name, locator, hashlib.sha256(self.state["value"]).hexdigest())

    def validate(self, token):
        if not self.state["connected"]:
            return AdapterResult("indeterminate", error_code="ConnectionError")
        fingerprint = hashlib.sha256(self.state["value"]).hexdigest()
        return AdapterResult("equivalent" if fingerprint == token.fingerprint else "changed")


class ExternalDeveloperSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.audit = Path(self.tmp.name) / "audit.jsonl"
        self.store = MemoryStore()

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_adapter_registers_and_disconnect_is_unverifiable(self):
        state = {"value": b"one", "connected": True}
        register_adapter("external-test", _ExternalAdapter(state))
        with guard(store=self.store, audit_path=self.audit):
            token = observe("record-1", adapter="external-test")
        state["connected"] = False
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx:
            self.assertEqual(ctx.check(token).state, FreshnessStatus.UNVERIFIABLE)

    def test_only_dependent_reasoning_invalidates(self):
        first = Path(self.tmp.name) / "first.txt"
        second = Path(self.tmp.name) / "second.txt"
        first.write_text("one")
        second.write_text("two")
        with guard(store=self.store, audit_path=self.audit):
            first_token, second_token = observe(first), observe(second)
            with reasoning("first-finding", [first_token]) as first_finding:
                pass
            with reasoning("second-finding", [second_token]) as second_finding:
                pass
        first.write_text("changed")
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx:
            self.assertEqual(ctx.check(first_token).state, FreshnessStatus.STALE_SOURCE)
            self.assertEqual(ctx.check(first_finding).state, FreshnessStatus.STALE_REASONING)
            self.assertEqual(ctx.check(second_finding).state, FreshnessStatus.CURRENT)


if __name__ == "__main__":
    unittest.main()
