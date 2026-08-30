"""Compare an ad-hoc pre-flight check with a declared FreshCtx dependency."""

from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


with TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "booking-status.txt"
    source.write_text("AVAILABLE", encoding="utf-8")

    # Ad-hoc baseline: each tool owns its own comparison and evidence format.
    expected = source.read_text(encoding="utf-8")
    source.write_text("BOOKED", encoding="utf-8")
    manual_allowed = source.read_text(encoding="utf-8") == expected
    print(f"MANUAL PREFLIGHT ALLOWED: {manual_allowed}")

    # FreshCtx: the dependency and reusable audit evidence are explicit.
    source.write_text("AVAILABLE", encoding="utf-8")
    store = MemoryStore()
    with guard(store=store, audit_path=root / "comparison-audit.jsonl"):
        status = observe(source)
        with reasoning("select_booking", [status]) as decision:
            pass
    source.write_text("BOOKED", encoding="utf-8")
    try:
        with guard(store=store, audit_path=root / "comparison-audit.jsonl") as ctx:
            ctx.run(lambda: print("BOOKED"), depends_on=[decision])
    except FreshnessBlocked as exc:
        print(f"FRESHCTX: {exc.result.state.value}; AUDIT_RESULTS={len(exc.result.adapter_results)}")
