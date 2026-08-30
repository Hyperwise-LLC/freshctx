"""A payment is approved from a balance that changes before execution."""

from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


with TemporaryDirectory() as directory:
    root = Path(directory)
    balance = root / "balance.txt"
    balance.write_text("1000", encoding="utf-8")
    store = MemoryStore()

    with guard(store=store, audit_path=root / "payment-audit.jsonl"):
        observed_balance = observe(balance)
        with reasoning("approve_payment", [observed_balance]) as approval:
            amount = 600

    # Another payment settles after approval.
    balance.write_text("400", encoding="utf-8")
    try:
        with guard(policy="require_approval", store=store, audit_path=root / "payment-audit.jsonl") as ctx:
            ctx.run(lambda: print(f"SENT {amount}"), depends_on=[approval])
    except FreshnessBlocked as exc:
        print(f"PAYMENT STOPPED: {exc.result.state.value}; {exc.result.policy_decision.upper()}")
