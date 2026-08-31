from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from freshctx import FreshnessBlocked, FreshnessState, MemoryStore, guard, observe, reasoning
from freshctx.adapters import ADAPTERS, StripeSubscriptionAdapter


class FakeStripeTransport:
    def __init__(self):
        self.status = "active"
        self.fail: Exception | None = None
        self.calls = []

    def __call__(self, subscription_id, api_key, api_version, timeout):
        self.calls.append((subscription_id, api_key, api_version, timeout))
        if self.fail is not None:
            raise self.fail
        return {
            "object": "subscription",
            "id": subscription_id,
            "status": self.status,
            "customer": "cus_test",
            "cancel_at_period_end": False,
            "items": {
                "data": [
                    {"id": "si_2", "price": {"id": "price_pro"}, "quantity": 2},
                    {"id": "si_1", "price": {"id": "price_base"}, "quantity": 1},
                ]
            },
        }


class StripeSubscriptionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audit = self.root / "audit.jsonl"
        self.store = MemoryStore()
        self.transport = FakeStripeTransport()
        self.adapter = StripeSubscriptionAdapter()
        self.original = ADAPTERS["stripe_subscription"]
        ADAPTERS["stripe_subscription"] = self.adapter

    def tearDown(self):
        ADAPTERS["stripe_subscription"] = self.original
        self.tmp.cleanup()

    def observe_subscription(self):
        with guard(store=self.store, audit_path=self.audit):
            return observe(
                "sub_test",
                adapter="stripe_subscription",
                api_key="sk_test_secret",
                api_version="2026-08-27.test",
                include_items=True,
                timeout=0.25,
                transport=self.transport,
            )

    def test_same_authoritative_subscription_is_current(self):
        token = self.observe_subscription()
        with guard(store=self.store, audit_path=self.audit) as ctx:
            result = ctx.check(token)
        self.assertEqual(result.state, FreshnessState.CURRENT)
        self.assertEqual(result.adapter_results[0]["evidence"]["changed_fields"], [])

    def test_material_subscription_change_blocks_protected_action(self):
        with guard(store=self.store, audit_path=self.audit):
            token = observe(
                "sub_test",
                adapter="stripe_subscription",
                api_key="sk_test_secret",
                fields=("status",),
                transport=self.transport,
            )
            with reasoning("grant_paid_access", [token]) as decision:
                pass
        self.transport.status = "canceled"
        calls = []
        with self.assertRaises(FreshnessBlocked) as raised:
            with guard(store=self.store, audit_path=self.audit) as ctx:
                ctx.run(lambda: calls.append("granted"), depends_on=[decision])
        self.assertEqual(calls, [])
        self.assertEqual(raised.exception.result.state, FreshnessState.STALE_REASONING)
        self.assertEqual(raised.exception.result.adapter_results[0]["evidence"]["changed_fields"], ["status"])

    def test_timeout_is_unverifiable_and_never_current(self):
        token = self.observe_subscription()
        self.transport.fail = TimeoutError("Stripe did not answer")
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx:
            result = ctx.check(token)
        self.assertEqual(result.state, FreshnessState.UNVERIFIABLE)
        self.assertEqual(result.adapter_results[0]["error_code"], "stripe_timeout")

    def test_missing_runtime_credentials_are_unverifiable(self):
        token = self.observe_subscription()
        result = StripeSubscriptionAdapter().validate(token)
        self.assertEqual(result.outcome, "indeterminate")
        self.assertEqual(result.error_code, "validation_inputs_unavailable")

    def test_deleted_subscription_is_changed(self):
        token = self.observe_subscription()
        self.transport.fail = urllib.error.HTTPError("https://api.stripe.com", 404, "missing", {}, None)
        result = self.adapter.validate(token)
        self.assertEqual(result.outcome, "changed")
        self.assertEqual(result.evidence["reason"], "subscription_missing")

    def test_secret_and_raw_subscription_values_are_not_persisted(self):
        token = self.observe_subscription()
        encoded = json.dumps(token.__dict__, sort_keys=True)
        self.assertNotIn("sk_test_secret", encoded)
        self.assertNotIn("cus_test", encoded)
        self.assertNotIn("price_pro", encoded)
        self.assertEqual(token.locator, "sub_test")

    def test_malformed_response_is_unverifiable(self):
        token = self.observe_subscription()
        self.transport.fail = None
        self.transport.__dict__["status"] = "active"

        def malformed(*_args):
            return {"object": "customer", "id": "cus_wrong"}

        self.adapter._runtime[token.id] = ("sk_test_secret", malformed)
        result = self.adapter.validate(token)
        self.assertEqual(result.outcome, "indeterminate")
        self.assertEqual(result.error_code, "ValueError")


if __name__ == "__main__":
    unittest.main()
