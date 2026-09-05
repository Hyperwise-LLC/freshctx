"""Create and verify a time-bounded receipt for one protected action."""

from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import MemoryStore, attest_correlation, guard, observe, reasoning, verify_attestation


def run_demo() -> dict[str, object]:
    key = b"demo-only-key-material-at-least-32-bytes"
    with TemporaryDirectory() as directory:
        source = Path(directory) / "account-state.txt"
        source.write_text("status=approved\n", encoding="utf-8")
        store = MemoryStore()
        with guard(store=store, audit_path=Path(directory) / "audit.jsonl") as ctx:
            evidence = observe(source)
            with reasoning("approve_action", depends_on=[evidence]) as decision:
                pass
            ctx.run(lambda: None, depends_on=[decision], boundary="payment.release")
        receipt = attest_correlation(
            ctx.correlation,
            issuer="demo-control",
            key_id="demo-key-1",
            key=key,
            ttl_seconds=300,
        )
        verified = verify_attestation(receipt, ctx.correlation, key=key)
        return {
            "freshness": ctx.correlation.freshness_state.value,
            "correlation_id": receipt.correlation_id,
            "attestation": verified.reason,
        }


if __name__ == "__main__":
    print(run_demo())
