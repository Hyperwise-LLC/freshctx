from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning
from freshctx.integrations.pre_action import PreActionBoundary, PreActionCall


ROOT = Path(__file__).resolve().parents[1]


class ActionEvidenceCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.first = self.root / "first.txt"
        self.second = self.root / "second.txt"
        self.first.write_text("one", encoding="utf-8")
        self.second.write_text("two", encoding="utf-8")
        self.audit = self.root / "audit.jsonl"
        self.store = MemoryStore()
        self.schema = json.loads(
            (ROOT / "schemas" / "action-evidence-correlation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.validator = Draft202012Validator(
            self.schema, format_checker=FormatChecker()
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _decision(self):
        with guard(store=self.store, audit_path=self.audit):
            first = observe(self.first)
            second = observe(self.second)
            with reasoning("choose_action", depends_on=[first, second]) as decision:
                pass
        return first, second, decision

    def test_allowed_action_correlates_the_reachable_evidence(self):
        first, second, decision = self._decision()
        executed = []
        with guard(
            store=self.store,
            audit_path=self.audit,
            run_id="framework-call-123",
        ) as ctx:
            result = ctx.run(
                lambda secret: executed.append("called") or "ok",
                "do-not-record",
                depends_on=[decision],
                boundary="test.action:write",
            )

        self.assertEqual(result, "ok")
        self.assertEqual(executed, ["called"])
        correlation = ctx.correlation
        self.assertIsNotNone(correlation)
        value = correlation.to_dict()
        self.validator.validate(value)
        self.assertEqual(value["run_id"], "framework-call-123")
        self.assertEqual(value["execution_id"], "framework-call-123")
        self.assertEqual(value["declared_dependency_ids"], [decision.id])
        self.assertEqual(value["reasoning_ids"], [decision.id])
        self.assertEqual(value["observation_ids"], sorted([first.id, second.id]))
        self.assertEqual(value["unresolved_dependency_ids"], [])
        self.assertEqual(value["freshness_state"], "CURRENT")
        self.assertEqual(value["boundary_outcome"], "allowed")
        self.assertNotIn("do-not-record", repr(value))

    def test_blocked_action_exposes_the_same_correlation_on_the_exception(self):
        first, second, decision = self._decision()
        self.first.write_text("changed", encoding="utf-8")
        executed = []

        with self.assertRaises(FreshnessBlocked) as raised:
            with guard(store=self.store, audit_path=self.audit) as ctx:
                ctx.run(
                    lambda: executed.append("called"),
                    depends_on=[decision],
                    boundary="test.action:write",
                )

        self.assertEqual(executed, [])
        correlation = raised.exception.correlation
        self.assertIsNotNone(correlation)
        self.assertIs(ctx.correlation, correlation)
        value = correlation.to_dict()
        self.validator.validate(value)
        self.assertEqual(value["freshness_state"], "STALE_REASONING")
        self.assertEqual(value["boundary_outcome"], "blocked")
        self.assertEqual(value["observation_ids"], sorted([first.id, second.id]))

    def test_unresolved_dependencies_are_recorded_without_becoming_current(self):
        with self.assertRaises(FreshnessBlocked) as raised:
            with guard(store=self.store, audit_path=self.audit) as ctx:
                ctx.run(lambda: None, depends_on=["missing-evidence"])

        value = raised.exception.correlation.to_dict()
        self.validator.validate(value)
        self.assertEqual(value["freshness_state"], "UNVERIFIABLE")
        self.assertEqual(value["declared_dependency_ids"], ["missing-evidence"])
        self.assertEqual(value["observation_ids"], [])
        self.assertEqual(value["unresolved_dependency_ids"], ["missing-evidence"])

    def test_pre_action_contract_adds_runtime_and_framework_action(self):
        _, _, decision = self._decision()
        boundary = PreActionBoundary(
            depends_on=[decision], store=self.store, audit_path=self.audit
        )
        result = boundary.invoke(
            PreActionCall(
                runtime="example-runtime",
                action="approve_payment",
                execution_id="tool-call-456",
            ),
            lambda: "approved",
        )

        self.assertEqual(result, "approved")
        correlation = boundary.last_correlation
        self.assertEqual(correlation.runtime, "example-runtime")
        self.assertEqual(correlation.action, "approve_payment")
        self.assertEqual(correlation.execution_id, "tool-call-456")

    def test_refresh_correlates_the_replacement_evidence_used_for_the_action(self):
        first, _, decision = self._decision()
        self.first.write_text("changed", encoding="utf-8")

        def refresh(_result):
            with guard(store=self.store, audit_path=self.audit):
                return observe(self.first)

        with guard(
            policy="refresh",
            store=self.store,
            audit_path=self.audit,
            refresh_callback=refresh,
        ) as ctx:
            self.assertEqual(
                ctx.run(lambda: "ok", depends_on=[decision]),
                "ok",
            )

        correlation = ctx.correlation
        self.validator.validate(correlation.to_dict())
        self.assertNotEqual(correlation.subject_id, decision.id)
        self.assertNotEqual(correlation.subject_id, first.id)
        self.assertEqual(correlation.observation_ids, (correlation.subject_id,))
        self.assertEqual(correlation.declared_dependency_ids, (decision.id,))

    def test_async_action_produces_a_correlation_record(self):
        async def scenario():
            _, _, decision = self._decision()
            with guard(store=self.store, audit_path=self.audit) as ctx:
                result = await ctx.run_async(
                    lambda: "ok", depends_on=[decision], boundary="async.action"
                )
            return result, ctx.correlation

        result, correlation = asyncio.run(scenario())
        self.assertEqual(result, "ok")
        self.validator.validate(correlation.to_dict())

    def test_audit_event_contains_the_portable_record_without_arguments(self):
        _, _, decision = self._decision()
        with guard(store=self.store, audit_path=self.audit) as ctx:
            ctx.run(
                lambda value: value,
                "private-business-payload",
                depends_on=[decision],
            )

        events = [
            json.loads(line)
            for line in self.audit.read_text(encoding="utf-8").splitlines()
        ]
        correlations = [
            event for event in events if event["event_type"] == "action_evidence_correlated"
        ]
        self.assertEqual(len(correlations), 1)
        self.validator.validate(correlations[0]["details"])
        self.assertNotIn("private-business-payload", repr(correlations[0]))


if __name__ == "__main__":
    unittest.main()
