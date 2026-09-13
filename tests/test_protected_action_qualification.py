from __future__ import annotations

import json
import runpy
import tempfile
import unittest
import warnings
from pathlib import Path

from freshctx import FreshnessBlocked, FreshnessState, MemoryStore, guard, observe, reasoning, register_adapter
from freshctx.integrations.pre_action import PreActionBoundary, PreActionCall
from freshctx.model import AdapterResult, ObservationToken


ROOT = Path(__file__).resolve().parents[1]


class CountingVersionAdapter:
    name = "qualification_counting_version"
    thread_safe = True

    def __init__(self, records: dict[str, int]) -> None:
        self.records = records
        self.validation_calls: list[str] = []

    def observe(self, locator: str) -> ObservationToken:
        return ObservationToken(self.name, locator, str(self.records[locator]))

    def validate(self, token: ObservationToken) -> AdapterResult:
        self.validation_calls.append(token.locator)
        current = str(self.records[token.locator])
        return AdapterResult(
            "equivalent" if current == token.fingerprint else "changed",
            evidence={"observed_revision": token.fingerprint, "current_revision": current},
        )


class ProtectedActionQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.audit = self.root / "qualification-audit.jsonl"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _filesystem_decision(self, store: MemoryStore, source: Path):
        with guard(store=store, audit_path=self.audit):
            token = observe(source)
            with reasoning("choose_action", depends_on=[token]) as decision:
                pass
        return decision

    def test_repeated_invocation_revalidates_and_blocks_second_attempt(self) -> None:
        source = self.root / "state.txt"
        source.write_text("version=1\n", encoding="utf-8")
        store = MemoryStore()
        decision = self._filesystem_decision(store, source)
        executions: list[str] = []
        protected = PreActionBoundary(
            depends_on=[decision],
            store=store,
            audit_path=self.audit,
        )
        call = PreActionCall(runtime="qualification", action="write", execution_id="retry-run")

        protected.invoke(call, lambda: executions.append("first"))
        source.write_text("version=2\n", encoding="utf-8")
        with self.assertRaises(FreshnessBlocked) as raised:
            protected.invoke(call, lambda: executions.append("second"))

        self.assertEqual(executions, ["first"])
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
        self.assertEqual(raised.exception.result.policy_decision, "block")
        self.assertEqual(raised.exception.correlation.boundary_outcome, "blocked")
        events = [json.loads(line) for line in self.audit.read_text(encoding="utf-8").splitlines()]
        retry_events = [event for event in events if event["run_id"] == "retry-run"]
        self.assertEqual(sum(event["event_type"] == "action_allowed" for event in retry_events), 1)
        correlations = [event for event in retry_events if event["event_type"] == "action_evidence_correlated"]
        self.assertEqual([event["details"]["boundary_outcome"] for event in correlations], ["allowed", "blocked"])

    def test_current_nested_boundaries_each_execute_once(self) -> None:
        source = self.root / "nested-current.txt"
        source.write_text("current\n", encoding="utf-8")
        store = MemoryStore()
        decision = self._filesystem_decision(store, source)
        executions: list[str] = []
        inner = PreActionBoundary(depends_on=[decision], store=store, audit_path=self.audit)
        outer = PreActionBoundary(depends_on=[decision], store=store, audit_path=self.audit)

        def outer_action() -> None:
            executions.append("outer")
            inner.invoke(
                PreActionCall(runtime="qualification", action="inner", execution_id="nested-inner"),
                lambda: executions.append("inner"),
            )

        outer.invoke(
            PreActionCall(runtime="qualification", action="outer", execution_id="nested-outer"),
            outer_action,
        )
        self.assertEqual(executions, ["outer", "inner"])

    def test_blocked_inner_boundary_never_starts_inner_action(self) -> None:
        outer_source = self.root / "outer.txt"
        inner_source = self.root / "inner.txt"
        outer_source.write_text("current\n", encoding="utf-8")
        inner_source.write_text("version=1\n", encoding="utf-8")
        store = MemoryStore()
        outer_decision = self._filesystem_decision(store, outer_source)
        inner_decision = self._filesystem_decision(store, inner_source)
        inner_source.write_text("version=2\n", encoding="utf-8")
        executions: list[str] = []
        inner = PreActionBoundary(depends_on=[inner_decision], store=store, audit_path=self.audit)
        outer = PreActionBoundary(depends_on=[outer_decision], store=store, audit_path=self.audit)

        def outer_action() -> None:
            executions.append("outer-started")
            inner.invoke(
                PreActionCall(runtime="qualification", action="inner", execution_id="blocked-inner"),
                lambda: executions.append("inner-started"),
            )

        with self.assertRaises(FreshnessBlocked) as raised:
            outer.invoke(
                PreActionCall(runtime="qualification", action="outer", execution_id="allowed-outer"),
                outer_action,
            )
        self.assertEqual(executions, ["outer-started"])
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
        self.assertEqual(raised.exception.correlation.execution_id, "blocked-inner")

    def test_shared_observation_is_validated_once_per_action_boundary(self) -> None:
        records = {"shared": 1}
        adapter = CountingVersionAdapter(records)
        register_adapter(adapter.name, adapter)
        store = MemoryStore()
        with guard(store=store, audit_path=self.audit):
            shared = observe("shared", adapter=adapter.name, freshness_strategy="version")
            with reasoning("left_branch", depends_on=[shared]) as left:
                pass
            with reasoning("right_branch", depends_on=[shared]) as right:
                pass
            with reasoning("combined", depends_on=[left, right]) as combined:
                pass

        executions: list[str] = []
        boundary = PreActionBoundary(depends_on=[combined], store=store, audit_path=self.audit)
        boundary.invoke(
            PreActionCall(runtime="qualification", action="shared", execution_id="shared-current"),
            lambda: executions.append("current"),
        )
        self.assertEqual(adapter.validation_calls, ["shared"])
        records["shared"] = 2
        with self.assertRaises(FreshnessBlocked) as raised:
            boundary.invoke(
                PreActionCall(runtime="qualification", action="shared", execution_id="shared-stale"),
                lambda: executions.append("stale"),
            )
        self.assertEqual(adapter.validation_calls, ["shared", "shared"])
        self.assertEqual(executions, ["current"])
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
        self.assertEqual(raised.exception.result.causes, (shared.id,))

    def test_existing_policy_results_remain_compatible(self) -> None:
        source = self.root / "policy.txt"
        source.write_text("version=1\n", encoding="utf-8")
        store = MemoryStore()
        decision = self._filesystem_decision(store, source)
        source.write_text("version=2\n", encoding="utf-8")

        for policy in ("allow", "warn"):
            executions: list[str] = []
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with guard(policy=policy, store=store, audit_path=self.audit) as ctx:
                    ctx.run(lambda: executions.append(policy), depends_on=[decision])
            self.assertEqual(executions, [policy])
            self.assertEqual(ctx.result.state, FreshnessState.STALE_REASONING)
            self.assertEqual(ctx.result.policy_decision, "allow")
            self.assertEqual(len(caught), 1 if policy == "warn" else 0)

        expected = {
            "block": "block",
            "refresh": "block",
            "replan": "replan",
            "require_approval": "require_approval",
        }
        for policy, decision_name in expected.items():
            executions = []
            with self.assertRaises(FreshnessBlocked) as raised:
                with guard(policy=policy, store=store, audit_path=self.audit) as ctx:
                    ctx.run(lambda: executions.append(policy), depends_on=[decision])
            self.assertEqual(executions, [])
            self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
            self.assertEqual(raised.exception.result.policy_decision, decision_name)

    def test_monotonic_version_detects_aba_before_action(self) -> None:
        module = runpy.run_path(ROOT / "examples" / "monotonic_evidence_version.py")
        result = module["run_demo"]()
        self.assertTrue(result["value_returned_to_original"])
        self.assertEqual(result["observed_revision"], 1)
        self.assertEqual(result["current_revision"], 3)
        self.assertEqual(result["freshness"], "STALE_SOURCE")
        self.assertEqual(result["action_executions"], 0)


if __name__ == "__main__":
    unittest.main()
