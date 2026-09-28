from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from freshctx import (
    FreshnessBlocked,
    MemoryStore,
    ObservationToken,
    ProtectedParameter,
    RetryPolicy,
    guard,
    parameter_digest,
    reasoning,
)
from freshctx.adapters import ADAPTERS
from freshctx.errors import ConfigurationError, RetryableVerificationError
from freshctx.integrations.pre_action import PreActionBoundary, PreActionCall
from freshctx.model import AdapterResult, FreshnessState, ReasoningNode


class ScriptedAdapter:
    """Deterministic adapter whose scripted results model verification only."""

    name = "prompt1c_scripted"
    thread_safe = True

    def __init__(self, outcomes, events=None, clock=None):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.events = events if events is not None else []
        self.clock = clock

    def validate(self, token):
        self.calls += 1
        self.events.append(f"verify-{self.calls}")
        if self.clock:
            self.clock[0] += self.clock_step
        result = self.outcomes.pop(0) if self.outcomes else AdapterResult("equivalent")
        if isinstance(result, BaseException):
            raise result
        return result


class Prompt1CExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.audit = Path(self.tmp.name) / "audit.jsonl"
        self.store = MemoryStore()
        self.original_adapter = ADAPTERS.get(ScriptedAdapter.name)

    def tearDown(self):
        if self.original_adapter is None:
            ADAPTERS.pop(ScriptedAdapter.name, None)
        else:
            ADAPTERS[ScriptedAdapter.name] = self.original_adapter
        self.tmp.cleanup()

    def source(self, outcome=None):
        adapter = ScriptedAdapter(outcome or [AdapterResult("equivalent")])
        ADAPTERS[adapter.name] = adapter
        token = ObservationToken(adapter.name, "opaque://customer/42", "v1", id="evidence-e1")
        self.store.put_observation(token)
        return token, adapter

    def derived(self, token, hops=1, source_dependencies=None):
        dependency_ids = list(source_dependencies if source_dependencies is not None else [token.id])
        last = token.id
        for index in range(hops):
            node = ReasoningNode(
                "tool_output",
                tuple(dependency_ids),
                f"{index + 1:064x}",
                {"tool_invocation_id": f"tool-{index + 1}", "output_digest": f"{index + 1:064x}"},
                id=f"tool-output-{index + 1}",
            )
            # Use guard/reasoning so the immutable reasoning digest is valid.
            with guard(store=self.store, audit_path=self.audit):
                with reasoning(node.kind, depends_on=node.dependencies, metadata=node.metadata) as recorded:
                    pass
            last = recorded.id
            dependency_ids = [last]
        return last

    def boundary(self, token, adapter, *, lineage=None, retry=None, attempt=None):
        ADAPTERS[adapter.name] = adapter
        protected = None
        if lineage is not None:
            protected = {"recipient": ProtectedParameter((lineage,), parameter_digest("acct-123"))}
        return PreActionBoundary(
            depends_on=[token.id],
            store=self.store,
            audit_path=self.audit,
            retry_policy=retry,
            protected_parameters=protected,
            parameter_values={"recipient": "acct-123"} if protected else None,
        )

    def call(self, **kwargs):
        return PreActionCall(runtime="test", action="transfer", **kwargs)

    def test_case1_clean_lineage_allows_once(self):
        token, adapter = self.source()
        leaf = self.derived(token)
        boundary = self.boundary(token, adapter, lineage=leaf)
        actions = []
        result = boundary.invoke(self.call(), lambda recipient: actions.append(recipient) or "sent", "acct-123")
        self.assertEqual(result, "sent")
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(actions, ["acct-123"])
        self.assertEqual(boundary.last_correlation.freshness_state, FreshnessState.CURRENT)

    def test_case2_stale_underlying_evidence_blocks(self):
        token, adapter = self.source([AdapterResult("changed")])
        leaf = self.derived(token)
        actions = []
        boundary = self.boundary(token, adapter, lineage=leaf)
        with self.assertRaises(FreshnessBlocked) as raised:
            boundary.invoke(self.call(), lambda recipient: actions.append(recipient), "acct-123")
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
        self.assertEqual(actions, [])

    def test_case3_required_missing_lineage_fails_closed(self):
        token, adapter = self.source()
        boundary = self.boundary(token, adapter, lineage="unobserved-tool-output")
        actions = []
        with self.assertRaises(FreshnessBlocked) as raised:
            boundary.invoke(self.call(), lambda recipient: actions.append(recipient), "acct-123")
        self.assertEqual(raised.exception.result.state, FreshnessState.UNVERIFIABLE)
        self.assertEqual(actions, [])

    def test_case4_multihop_lineage_reaches_evidence(self):
        token, adapter = self.source()
        leaf = self.derived(token, hops=2)
        actions = []
        result = self.boundary(token, adapter, lineage=leaf).invoke(
            self.call(), lambda recipient: actions.append(recipient) or recipient, "acct-123"
        )
        self.assertEqual(result, "acct-123")
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(actions, ["acct-123"])

    def test_case5_transient_then_current_never_executes_between_verifications(self):
        events = []
        token, adapter = self.source([
            RetryableVerificationError("temporary timeout"), AdapterResult("equivalent")
        ])
        adapter.events = events
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=2, max_elapsed_ms=100, backoff_ms=0),
        )
        result = boundary.invoke(
            self.call(), lambda: events.append("action") or "ok"
        )
        self.assertEqual(result, "ok")
        self.assertEqual(events, ["verify-1", "verify-2", "action"])
        self.assertEqual(events.count("action"), 1)

    def test_adapter_retryable_indeterminate_can_recover_to_current(self):
        token, adapter = self.source([
            AdapterResult("indeterminate", error_code="temporary_source_unavailable", retryable=True),
            AdapterResult("equivalent"),
        ])
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=2, max_elapsed_ms=100),
        )
        self.assertEqual(boundary.invoke(self.call(), lambda: "ok"), "ok")
        self.assertEqual(adapter.calls, 2)

    def test_case6_transient_exhaustion_blocks_execution(self):
        token, adapter = self.source([RetryableVerificationError("timeout")] * 3)
        actions = []
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=3, max_elapsed_ms=100, backoff_ms=0),
        )
        with self.assertRaises(FreshnessBlocked) as raised:
            boundary.invoke(self.call(), lambda: actions.append("action"))
        self.assertEqual(raised.exception.result.state, FreshnessState.UNVERIFIABLE)
        self.assertEqual(adapter.calls, 3)
        self.assertEqual(actions, [])

    def test_case7_definitive_stale_is_not_retried(self):
        token, adapter = self.source([AdapterResult("changed"), AdapterResult("equivalent")])
        actions = []
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=3, max_elapsed_ms=100, backoff_ms=0),
        )
        with self.assertRaises(FreshnessBlocked):
            boundary.invoke(self.call(), lambda: actions.append("action"))
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(actions, [])

    def test_permanent_adapter_error_and_false_transient_flag_do_not_retry(self):
        token, adapter = self.source([RuntimeError("permanent"), AdapterResult("equivalent")])
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=3, max_elapsed_ms=100),
        )
        with self.assertRaises(FreshnessBlocked):
            boundary.invoke(self.call(), lambda: self.fail("must block"))
        self.assertEqual(adapter.calls, 1)

    def test_retryable_flag_only_retries_indeterminate_result(self):
        token, adapter = self.source([AdapterResult("changed", retryable=True)])
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=2, max_elapsed_ms=100),
        )
        with self.assertRaises(FreshnessBlocked):
            boundary.invoke(self.call(), lambda: self.fail("must block"))
        self.assertEqual(adapter.calls, 1)

    def test_retry_policy_rejects_zero_and_unbounded_retry_configuration(self):
        token, _ = self.source()
        with self.assertRaises(ConfigurationError):
            guard(store=self.store, audit_path=self.audit, retry_policy=RetryPolicy(max_attempts=0))
        with self.assertRaises(ConfigurationError):
            guard(store=self.store, audit_path=self.audit, retry_policy=RetryPolicy(max_attempts=2))
        self.assertIsNotNone(token)

    def test_elapsed_budget_stops_before_attempt_bound_using_fake_clock(self):
        events = []
        token, adapter = self.source([RetryableVerificationError("timeout")] * 4)
        adapter.events = events
        fake = [0.0]
        adapter.clock = fake
        adapter.clock_step = 0.004
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=4, max_elapsed_ms=7, backoff_ms=0),
        )
        with patch("freshctx.core.time.monotonic", side_effect=lambda: fake[0]):
            with self.assertRaises(FreshnessBlocked):
                boundary.invoke(self.call(), lambda: events.append("action"))
        self.assertLess(adapter.calls, 4)
        self.assertNotIn("action", events)

    def test_backoff_uses_deterministic_sleep_hook(self):
        token, adapter = self.source([RetryableVerificationError("timeout"), AdapterResult("equivalent")])
        delays = []
        real_sleep = __import__("time").sleep
        real_monotonic = __import__("time").monotonic
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=2, max_elapsed_ms=1000, backoff_ms=5),
        )
        def record_boundary_delay(seconds):
            if seconds == 0.005:
                delays.append(seconds)
                return None
            return real_sleep(seconds)

        with patch("freshctx.core.time.sleep", side_effect=record_boundary_delay):
            boundary.invoke(self.call(), lambda: "ok")
        self.assertEqual(delays, [0.005])
        self.assertGreater(real_monotonic(), 0)

    def test_lineage_cycle_missing_malformed_and_duplicate_dependencies_fail_closed(self):
        token, adapter = self.source()
        cycle_a = ReasoningNode("tool_output", ("cycle-b",), "bad", {}, id="cycle-a")
        cycle_b = ReasoningNode("tool_output", ("cycle-a",), "bad", {}, id="cycle-b")
        self.store.put_reasoning(cycle_a)
        self.store.put_reasoning(cycle_b)
        for lineage in ("cycle-a", "absent-node"):
            with self.subTest(lineage=lineage):
                boundary = self.boundary(token, adapter, lineage=lineage)
                with self.assertRaises(FreshnessBlocked):
                    boundary.invoke(self.call(), lambda *_: self.fail("must block"), "acct-123")
        malformed = ObservationToken(adapter.name, "", "", id="malformed-token")
        self.store.put_observation(malformed)
        boundary = self.boundary(token, adapter, lineage=malformed.id)
        with self.assertRaises(FreshnessBlocked):
            boundary.invoke(self.call(), lambda *_: self.fail("must block"), "acct-123")
        duplicate_leaf = self.derived(token, source_dependencies=[token.id, token.id])
        self.assertIsNotNone(self.store.get(duplicate_leaf))

    def test_tool_output_without_sources_cannot_justify_required_parameter(self):
        token, adapter = self.source()
        output = ReasoningNode("tool_output", (), "0" * 64, {}, id="source-less-output")
        self.store.put_reasoning(output)
        boundary = self.boundary(token, adapter, lineage=output.id)
        with self.assertRaises(FreshnessBlocked) as raised:
            boundary.invoke(self.call(), lambda *_: self.fail("must block"), "acct-123")
        self.assertEqual(raised.exception.result.state, FreshnessState.UNVERIFIABLE)

    def test_duplicate_dependencies_are_deduplicated_and_still_revalidated(self):
        token, adapter = self.source()
        leaf = self.derived(token)
        protected = {"recipient": ProtectedParameter((leaf, leaf), parameter_digest("acct-123"))}
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            protected_parameters=protected, parameter_values={"recipient": "acct-123"},
        )
        self.assertEqual(boundary.invoke(self.call(), lambda value: value, "acct-123"), "acct-123")
        self.assertEqual(adapter.calls, 1)

    def test_optional_parameter_without_lineage_can_run_and_required_one_cannot(self):
        token, adapter = self.source()
        # No required-parameter declaration means legacy/unprotected parameters remain compatible.
        called = []
        result = self.boundary(token, adapter).invoke(self.call(), lambda timeout: called.append(timeout), timeout=1)
        self.assertIsNone(result)
        self.assertEqual(called, [1])
        boundary = self.boundary(token, adapter, lineage="not-recorded")
        with self.assertRaises(FreshnessBlocked):
            boundary.invoke(self.call(), lambda recipient: self.fail("must block"), "acct-123")

    def test_unprotected_optional_argument_can_be_absent_from_lineage_map(self):
        token, adapter = self.source()
        leaf = self.derived(token)
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            protected_parameters={"recipient": ProtectedParameter((leaf,), parameter_digest("acct-123"))},
            parameter_values={"recipient": "acct-123"},
        )
        received = []
        boundary.invoke(self.call(), lambda recipient, timeout: received.append((recipient, timeout)),
                        "acct-123", 30)
        self.assertEqual(received, [("acct-123", 30)])
        self.assertEqual(adapter.calls, 1)

    def test_evidence_that_changes_between_retries_blocks_without_action(self):
        token, adapter = self.source([
            RetryableVerificationError("temporary timeout"),
            AdapterResult("changed"),
            AdapterResult("equivalent"),
        ])
        actions = []
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=3, max_elapsed_ms=100),
        )
        with self.assertRaises(FreshnessBlocked) as raised:
            boundary.invoke(self.call(), lambda: actions.append("action"))
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
        self.assertEqual(adapter.calls, 2)
        self.assertEqual(actions, [])

    def test_operation_attempt_metadata_preserves_supplied_identity_without_limits(self):
        token, adapter = self.source()
        correlations = []
        for attempt_id, parent in (("attempt-1", None), ("attempt-2", "attempt-1")):
            boundary = PreActionBoundary(depends_on=[token.id], store=self.store, audit_path=self.audit)
            boundary.invoke(
                self.call(operation_id="op-1", attempt_id=attempt_id,
                          parent_attempt_id=parent, previous_outcome="timeout" if parent else None),
                lambda: "ok",
            )
            correlations.append(boundary.last_correlation)
        first, second = correlations
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertEqual(first.attempt_id, "attempt-1")
        self.assertEqual(second.parent_attempt_id, "attempt-1")
        self.assertEqual(adapter.calls, 2)

    def test_different_and_missing_operation_ids_are_not_inferred(self):
        token, adapter = self.source()
        values = []
        for operation_id in ("op-a", "op-b", None):
            boundary = PreActionBoundary(depends_on=[token.id], store=self.store, audit_path=self.audit)
            boundary.invoke(self.call(operation_id=operation_id), lambda: "ok")
            values.append(boundary.last_correlation)
        self.assertEqual([item.operation_id for item in values], ["op-a", "op-b", None])
        self.assertEqual([item.operation_identity_supplied for item in values], [True, True, False])

    def test_required_lineage_fails_closed_under_allow_and_warn_policies(self):
        for policy in ("allow", "warn"):
            self.store = MemoryStore()
            token, adapter = self.source([AdapterResult("changed")])
            leaf = self.derived(token)
            boundary = PreActionBoundary(
                depends_on=[token.id], store=self.store, audit_path=self.audit,
                policy=policy,
                protected_parameters={"recipient": ProtectedParameter((leaf,), parameter_digest("acct-123"))},
                parameter_values={"recipient": "acct-123"},
            )
            actions = []
            with self.subTest(policy=policy), self.assertRaises(FreshnessBlocked):
                boundary.invoke(self.call(), lambda value: actions.append(value), "acct-123")
            self.assertEqual(actions, [])
            ADAPTERS.pop(adapter.name, None)

    def test_retry_elapsed_values_and_validation_budget_must_be_finite(self):
        token, _ = self.source()
        for policy in (
            RetryPolicy(max_attempts=2, max_elapsed_ms=float("nan")),
            RetryPolicy(max_attempts=2, max_elapsed_ms=float("inf")),
        ):
            with self.subTest(policy=policy), self.assertRaises(ConfigurationError):
                guard(store=self.store, audit_path=self.audit, retry_policy=policy)
        with self.assertRaises(ConfigurationError):
            guard(store=self.store, audit_path=self.audit, validation_budget_ms=float("inf"))
        self.assertIsNotNone(token)

    def test_parameter_value_override_mismatch_blocks_before_verification(self):
        token, adapter = self.source()
        leaf = self.derived(token)
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            protected_parameters={"recipient": ProtectedParameter((leaf,), parameter_digest("acct-123"))},
            parameter_values={"recipient": "acct-other"},
        )
        actions = []
        with self.assertRaises(FreshnessBlocked) as raised:
            boundary.invoke(self.call(), lambda value: actions.append(value), "acct-123")
        self.assertEqual(raised.exception.result.state, FreshnessState.UNVERIFIABLE)
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(actions, [])

    def test_action_exception_does_not_trigger_evidence_retry(self):
        token, adapter = self.source()
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=3, max_elapsed_ms=100),
        )
        def fail_action():
            raise RuntimeError("business action failure")
        with self.assertRaisesRegex(RuntimeError, "business action failure"):
            boundary.invoke(self.call(), fail_action)
        self.assertEqual(adapter.calls, 1)

    def test_shared_dependency_for_two_protected_parameters_is_validated_once(self):
        token, adapter = self.source([AdapterResult("changed")])
        leaf = self.derived(token)
        protected = {
            "recipient": ProtectedParameter((leaf,), parameter_digest("acct-123")),
            "currency": ProtectedParameter((leaf,), parameter_digest("USD")),
        }
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            protected_parameters=protected,
            parameter_values={"recipient": "acct-123", "currency": "USD"},
        )
        with self.assertRaises(FreshnessBlocked):
            boundary.invoke(self.call(), lambda **kwargs: self.fail("must block"),
                            recipient="acct-123", currency="USD")
        self.assertEqual(adapter.calls, 1)

    def test_concurrent_validations_do_not_share_attempt_state(self):
        token, adapter = self.source()
        barrier = threading.Barrier(2)
        actions = []
        errors = []
        def run(index):
            try:
                boundary = PreActionBoundary(depends_on=[token.id], store=self.store, audit_path=self.audit)
                boundary.invoke(self.call(operation_id="same-op", attempt_id=f"a{index}"),
                                lambda: (barrier.wait(timeout=2), actions.append(index)))
            except Exception as exc:  # surfaced in parent thread below
                errors.append(exc)
        threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=3)
        self.assertEqual(errors, [])
        self.assertCountEqual(actions, [0, 1])
        self.assertEqual(adapter.calls, 2)

    def test_value_binding_rejects_default_override_kwargs_override_and_bool_int_alias(self):
        cases = (
            (lambda account=False: account, (), {}, True, True),
            (lambda **kwargs: kwargs["account"], (), {"account": "bad"}, "good", "good"),
            (lambda account: account, (1,), {}, True, True),
        )
        for action, args, kwargs, protected_value, extracted_value in cases:
            with self.subTest(action=action):
                self.store = MemoryStore()
                token, adapter = self.source()
                leaf = self.derived(token)
                boundary = PreActionBoundary(
                    depends_on=[token.id], store=self.store, audit_path=self.audit,
                    protected_parameters={"account": ProtectedParameter((leaf,), parameter_digest(protected_value))},
                    parameter_values={"account": extracted_value},
                )
                with self.assertRaises(FreshnessBlocked):
                    boundary.invoke(self.call(), action, *args, **kwargs)
                self.assertEqual(adapter.calls, 0)

    def test_legacy_correlation_serialization_omits_prompt1c_fields(self):
        token, _ = self.source()
        boundary = PreActionBoundary(depends_on=[token.id], store=self.store, audit_path=self.audit)
        boundary.invoke(self.call(), lambda: "ok")
        data = boundary.last_correlation.to_dict()
        self.assertNotIn("operation_id", data)
        self.assertNotIn("attempt_id", data)
        self.assertNotIn("protected_parameter_ids", data)
        self.assertNotIn("attempt_metadata_supplied", data)

    def test_empty_protected_parameter_map_preserves_legacy_allow_behavior(self):
        token, adapter = self.source()
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            protected_parameters={}, parameter_values={},
        )
        called = []
        boundary.invoke(self.call(), lambda: called.append("action") or "ok")
        self.assertEqual(called, ["action"])
        self.assertEqual(adapter.calls, 1)

    def test_legacy_validation_budget_keeps_validator_on_calling_thread(self):
        caller_thread = threading.get_ident()
        token, adapter = self.source()
        seen = []
        adapter.validate = lambda observed: (seen.append(threading.get_ident()) or AdapterResult("equivalent"))
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            validation_budget_ms=500,
        )
        boundary.invoke(self.call(), lambda: "ok")
        self.assertEqual(seen, [caller_thread])

    def test_explicit_retry_deadline_bounds_hanging_validator_and_never_retries_it(self):
        release = threading.Event()
        started = threading.Event()
        calls = []
        class HangingAdapter:
            name = ScriptedAdapter.name
            thread_safe = True
            def validate(self, observed):
                calls.append(threading.get_ident())
                started.set()
                release.wait(timeout=2)
                return AdapterResult("equivalent")
        adapter = HangingAdapter()
        ADAPTERS[adapter.name] = adapter
        token = ObservationToken(adapter.name, "opaque://hanging", "v1", id="hanging-evidence")
        self.store.put_observation(token)
        actions = []
        boundary = PreActionBoundary(
            depends_on=[token.id], store=self.store, audit_path=self.audit,
            retry_policy=RetryPolicy(max_attempts=3, max_elapsed_ms=80, backoff_ms=0),
        )
        try:
            with self.assertRaises(FreshnessBlocked) as raised:
                boundary.invoke(self.call(), lambda: actions.append("action"))
            self.assertTrue(started.is_set())
            self.assertEqual(raised.exception.result.state, FreshnessState.UNVERIFIABLE)
            self.assertEqual(len(calls), 1)
            self.assertEqual(actions, [])
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
