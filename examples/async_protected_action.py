"""Protect an asynchronous action without blocking the event loop."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "approval.txt"
        source.write_text("approved", encoding="utf-8")
        store = MemoryStore()
        async with guard(store=store, audit_path=root / "audit.jsonl"):
            approval = observe(source)
            with reasoning("send_payment", [approval]) as decision:
                pass
        source.write_text("revoked", encoding="utf-8")
        try:
            async with guard(store=store, audit_path=root / "audit.jsonl") as ctx:
                await ctx.run_async(asyncio.sleep, 0, depends_on=[decision])
        except FreshnessBlocked as blocked:
            print(f"ASYNC ACTION BLOCKED: {blocked.result.state.value}")


if __name__ == "__main__":
    asyncio.run(main())
