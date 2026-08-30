import json
import runpy
import tempfile
import time
import unittest
from pathlib import Path

from freshctx import ConfigurationError, FreshnessBlocked, FreshnessState, MemoryStore, guard, observe, reasoning, register_adapter
from freshctx.model import AdapterResult, ObservationToken


class SlowAdapter:
    name = "slow-test"
    thread_safe = True

    def __init__(self, delay=0.04):
        self.delay = delay
        self.calls = 0

    def observe(self, locator, **_options):
        return ObservationToken(self.name, str(locator), str(locator))

    def validate(self, token):
        self.calls += 1
        time.sleep(self.delay)
        return AdapterResult("equivalent", evidence={"locator": token.locator})


class UnsafeAdapter(SlowAdapter):
    name = "unsafe-test"
    thread_safe = False

    def __init__(self, delay=0.01):
        super().__init__(delay)
        self.active = 0
        self.max_active = 0

    def validate(self, token):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            return super().validate(token)
        finally:
            self.active -= 1


class FeedbackFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audit = self.root / "audit.jsonl"
        self.store = MemoryStore()
        self.adapter = SlowAdapter()
        register_adapter(self.adapter.name, self.adapter)

    def tearDown(self):
        self.tmp.cleanup()

    def build_wide(self, count=4):
        with guard(store=self.store, audit_path=self.audit):
            tokens = [observe(str(index), adapter=self.adapter.name) for index in range(count)]
            with reasoning("wide", tokens) as node:
                pass
        return tokens, node

    def test_concurrency_is_opt_in_and_reduces_wide_graph_latency(self):
        _tokens, node = self.build_wide()
        started = time.monotonic()
        with guard(store=self.store, audit_path=self.audit) as ctx:
            sequential = ctx.check(node)
        sequential_seconds = time.monotonic() - started

        started = time.monotonic()
        with guard(store=self.store, audit_path=self.audit, validation_workers=4) as ctx:
            concurrent = ctx.check(node)
        concurrent_seconds = time.monotonic() - started

        self.assertEqual(sequential.state, FreshnessState.CURRENT)
        self.assertEqual(concurrent.state, FreshnessState.CURRENT)
        self.assertLess(concurrent_seconds, sequential_seconds * 0.7)
        self.assertTrue(all("duration_ms" in item["evidence"] for item in concurrent.adapter_results))

    def test_duplicate_dependency_is_validated_once_per_check(self):
        tokens, _node = self.build_wide(1)
        with guard(store=self.store, audit_path=self.audit):
            with reasoning("deduplicated", [tokens[0], tokens[0]]) as node:
                pass
        before = self.adapter.calls
        with guard(store=self.store, audit_path=self.audit, validation_workers=4) as ctx:
            ctx.check(node)
        self.assertEqual(self.adapter.calls - before, 1)

    def test_budget_marks_unfinished_validation_unverifiable(self):
        _tokens, node = self.build_wide(3)
        with guard(policy="allow", store=self.store, audit_path=self.audit, validation_workers=2, validation_budget_ms=5) as ctx:
            result = ctx.check(node)
        self.assertEqual(result.state, FreshnessState.UNVERIFIABLE)
        self.assertIn("validation_budget_exceeded", {item.get("error_code") for item in result.adapter_results})
        calls_after_return = self.adapter.calls
        time.sleep(self.adapter.delay * 1.5)
        self.assertEqual(self.adapter.calls, calls_after_return, "no validator may continue after check() returns")

    def test_custom_adapter_is_sequential_until_it_declares_thread_safety(self):
        adapter = UnsafeAdapter()
        register_adapter(adapter.name, adapter)
        with guard(store=self.store, audit_path=self.audit):
            tokens = [observe(str(index), adapter=adapter.name) for index in range(3)]
            with reasoning("unsafe-wide", tokens) as node:
                pass
        with guard(store=self.store, audit_path=self.audit, validation_workers=3) as ctx:
            result = ctx.check(node)
        self.assertEqual(result.state, FreshnessState.CURRENT)
        self.assertEqual(adapter.max_active, 1)
        self.assertEqual({item["evidence"]["validation_execution"] for item in result.adapter_results}, {"sequential"})

    def test_ttl_and_explicit_unverifiable_strategies(self):
        with guard(store=self.store, audit_path=self.audit):
            ttl = observe("ttl", adapter=self.adapter.name, freshness_strategy="ttl", max_age_seconds=0.001)
            unknown = observe("ambient", adapter=self.adapter.name, freshness_strategy="unverifiable")
        time.sleep(0.005)
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx:
            expired = ctx.check(ttl)
            unverifiable = ctx.check(unknown)
        self.assertEqual(expired.state, FreshnessState.STALE_SOURCE)
        self.assertEqual(unverifiable.state, FreshnessState.UNVERIFIABLE)

    def test_adapter_owned_strategy_is_reported_without_inventing_semantics(self):
        with guard(store=self.store, audit_path=self.audit):
            versioned = observe("versioned", adapter=self.adapter.name, freshness_strategy="version")
        with guard(store=self.store, audit_path=self.audit) as ctx:
            result = ctx.check(versioned)
        self.assertEqual(result.state, FreshnessState.CURRENT)
        self.assertEqual(result.adapter_results[0]["evidence"]["freshness_strategy"], "version")

    def test_replan_and_renewed_approval_remain_policy_decisions(self):
        source = self.root / "approval.json"
        source.write_text('{"slot":"10:00"}', encoding="utf-8")
        with guard(store=self.store, audit_path=self.audit):
            token = observe(source)
        source.write_text('{"slot":"11:00"}', encoding="utf-8")
        for policy in ("replan", "require_approval"):
            with self.assertRaises(FreshnessBlocked) as raised:
                with guard(policy=policy, store=self.store, audit_path=self.audit) as ctx:
                    ctx.run(lambda: None, depends_on=[token])
            self.assertEqual(raised.exception.result.state, FreshnessState.STALE_SOURCE)
            self.assertEqual(raised.exception.result.policy_decision, policy)

    def test_invalid_feedback_options_fail_early(self):
        with self.assertRaises(ConfigurationError):
            guard(validation_workers=0)
        with guard(store=self.store, audit_path=self.audit):
            with self.assertRaises(ConfigurationError):
                observe("x", adapter=self.adapter.name, freshness_strategy="ttl")

    def test_audit_retains_schema_v1_and_adds_validation_details(self):
        _tokens, node = self.build_wide(2)
        with guard(store=self.store, audit_path=self.audit, validation_workers=2) as ctx:
            ctx.check(node)
        events = [json.loads(line) for line in self.audit.read_text(encoding="utf-8").splitlines()]
        applied = [event for event in events if event["event_type"] == "policy_applied"][-1]
        self.assertEqual(applied["schema_version"], 1)
        self.assertEqual(applied["details"]["validation"]["workers"], 2)

    def test_benchmark_adapter_explicitly_opts_into_concurrency(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_validation.py"
        module = runpy.run_path(script)
        self.assertIs(module["DelayedAdapter"].thread_safe, True)


if __name__ == "__main__":
    unittest.main()
