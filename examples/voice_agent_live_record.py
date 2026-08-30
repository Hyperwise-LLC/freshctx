"""Voice-agent boundary: semantic validation plus FreshCtx revalidation.

FreshCtx does not decide whether speech recognition produced the correct name.
The application compares the spoken-back value with the canonical record, while
FreshCtx ensures that record is still the one supporting the protected action.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


def continue_call(customer_name: str) -> None:
    print(f"CONTINUED for {customer_name}")


with TemporaryDirectory() as directory:
    root = Path(directory)
    customer = root / "customer.txt"
    customer.write_text("Ada Lovelace", encoding="utf-8")
    store = MemoryStore()

    with guard(store=store, audit_path=root / "voice-audit.jsonl"):
        canonical = observe(customer)
        spoken_back = "Ada Lovelace"
        if spoken_back != customer.read_text(encoding="utf-8"):
            raise ValueError("ask the caller instead of guessing")
        with reasoning("confirm_customer_name", [canonical]) as decision:
            confirmed_name = spoken_back

    # The canonical record changes while the live conversation continues.
    customer.write_text("Augusta Ada King", encoding="utf-8")

    try:
        with guard(store=store, audit_path=root / "voice-audit.jsonl") as ctx:
            ctx.run(continue_call, confirmed_name, depends_on=[decision])
    except FreshnessBlocked as exc:
        print(f"ASK AGAIN: {exc.result.state.value}")
