"""A calendar slot changes after approval but before booking."""

from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


with TemporaryDirectory() as directory:
    root = Path(directory)
    slot = root / "slot.txt"
    slot.write_text("10:00 AVAILABLE", encoding="utf-8")
    store = MemoryStore()

    with guard(store=store, audit_path=root / "booking-audit.jsonl"):
        availability = observe(slot)
        with reasoning("approve_booking", [availability]) as approval:
            selected = "10:00"

    slot.write_text("10:00 BOOKED", encoding="utf-8")
    try:
        with guard(policy="require_approval", store=store, audit_path=root / "booking-audit.jsonl") as ctx:
            ctx.run(lambda: print(f"BOOKED {selected}"), depends_on=[approval])
    except FreshnessBlocked as exc:
        print(f"{exc.result.policy_decision.upper()}: {exc.result.state.value}")
