"""A stale webhook snapshot disagrees with the authoritative Stripe record."""

from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


authoritative = {"status": "active"}


def stripe_test_transport(subscription_id, _api_key, _api_version, _timeout):
    return {
        "object": "subscription",
        "id": subscription_id,
        "status": authoritative["status"],
        "customer": "cus_demo",
        "cancel_at_period_end": False,
    }


with TemporaryDirectory() as directory:
    root = Path(directory)
    store = MemoryStore()

    with guard(store=store, audit_path=root / "stripe-audit.jsonl"):
        subscription = observe(
            "sub_demo",
            adapter="stripe_subscription",
            api_key="sk_test_not_a_real_key",
            fields=("status",),
            transport=stripe_test_transport,
        )
        with reasoning("grant_paid_access", [subscription]) as access_decision:
            pass

    # The webhook-derived application snapshot still says active, but Stripe's
    # authoritative Subscription has changed before access is granted.
    authoritative["status"] = "canceled"
    try:
        with guard(store=store, audit_path=root / "stripe-audit.jsonl") as ctx:
            ctx.run(lambda: print("ACCESS GRANTED"), depends_on=[access_decision])
    except FreshnessBlocked as exc:
        print(f"BLOCKED: {exc.result.state.value}")
