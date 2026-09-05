import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from freshctx import (
    MemoryStore,
    ObservedReadCapture,
    ProvenanceBlocked,
    ProvenanceBoundary,
    guard,
    observe,
)


ROOT = Path(__file__).resolve().parents[1]


class ProvenanceEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.authoritative = self.root / "authoritative.csv"
        self.decoy = self.root / "final.csv"
        self.authoritative.write_text("account,total\nA,10\n", encoding="utf-8")
        self.decoy.write_text("account,total\nA,8\n", encoding="utf-8")
        self.store = MemoryStore()

    def tearDown(self):
        self.tmp.cleanup()

    def _observe(self, path):
        with guard(store=self.store):
            return observe(path)

    def test_consistent_provenance_executes_action_once(self):
        capture = ObservedReadCapture(self.root)
        capture.read_text("authoritative.csv")
        source = self._observe(self.authoritative)
        executions = []
        boundary = ProvenanceBoundary(capture)
        with guard(store=self.store) as ctx:
            value = boundary.invoke(
                ctx,
                lambda: executions.append("ran") or "done",
                depends_on=[source],
                selected_source="authoritative.csv",
                cited_sources=("authoritative.csv",),
                required_sources=("authoritative.csv",),
            )
        self.assertEqual(value, "done")
        self.assertEqual(executions, ["ran"])
        self.assertEqual(boundary.last_enforcement.boundary_outcome, "allowed")

    def test_current_decoy_is_blocked_by_separate_provenance_policy(self):
        capture = ObservedReadCapture(self.root)
        capture.read_text("final.csv")
        source = self._observe(self.decoy)
        executions = []
        boundary = ProvenanceBoundary(capture)
        with guard(store=self.store) as ctx:
            with self.assertRaises(ProvenanceBlocked) as raised:
                boundary.invoke(
                    ctx,
                    lambda: executions.append("ran"),
                    depends_on=[source],
                    selected_source="final.csv",
                    cited_sources=("final.csv",),
                    required_sources=("authoritative.csv",),
                )
        self.assertEqual(executions, [])
        self.assertEqual(raised.exception.receipt.freshness_state.value, "CURRENT")
        self.assertEqual(raised.exception.receipt.provenance_assessment.value, "INCONSISTENT")
        self.assertEqual(raised.exception.enforcement.boundary_outcome, "blocked")

    def test_not_assessed_is_fail_closed_by_default_and_configurable(self):
        capture = ObservedReadCapture(self.root)
        capture.read_text("authoritative.csv")
        source = self._observe(self.authoritative)
        with guard(store=self.store) as ctx:
            with self.assertRaises(ProvenanceBlocked):
                ProvenanceBoundary(capture).invoke(ctx, lambda: None, depends_on=[source])
        with guard(store=self.store) as ctx:
            result = ProvenanceBoundary(capture, on_not_assessed="allow").invoke(
                ctx, lambda: "allowed", depends_on=[source]
            )
        self.assertEqual(result, "allowed")

    def test_async_action_is_blocked_before_execution(self):
        async def scenario():
            capture = ObservedReadCapture(self.root)
            capture.read_text("final.csv")
            source = self._observe(self.decoy)
            executions = []
            async with guard(store=self.store) as ctx:
                with self.assertRaises(ProvenanceBlocked):
                    await ProvenanceBoundary(capture).invoke_async(
                        ctx,
                        lambda: executions.append("ran"),
                        depends_on=[source],
                        selected_source="final.csv",
                        required_sources=("authoritative.csv",),
                    )
            self.assertEqual(executions, [])

        asyncio.run(scenario())

    def test_enforcement_record_matches_public_schema(self):
        capture = ObservedReadCapture(self.root)
        capture.read_text("authoritative.csv")
        source = self._observe(self.authoritative)
        boundary = ProvenanceBoundary(capture)
        with guard(store=self.store) as ctx:
            boundary.invoke(
                ctx,
                lambda: None,
                depends_on=[source],
                selected_source="authoritative.csv",
                required_sources=("authoritative.csv",),
            )
        schema = json.loads((ROOT / "schemas/provenance-enforcement.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(
            boundary.last_enforcement.to_dict()
        )


if __name__ == "__main__":
    unittest.main()
