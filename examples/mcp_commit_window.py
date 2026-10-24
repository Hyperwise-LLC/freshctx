"""Show the gap between MCP handler admission and an application commit.

This synthetic, in-process example uses the optional official MCP Python SDK v2.
It is not a distributed transaction or a production correctness guarantee.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from mcp import Client
from mcp.server.mcpserver import MCPServer

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.mcp_guard import FreshCtxMCPGuard


WAIT_SECONDS = 5


async def run_case(mutate_after_admission: bool, check_version: bool) -> dict[str, object]:
    """Admit a handler, optionally mutate, then attempt its old decision's write."""
    record = {"version": 0, "value": 0}
    lock = asyncio.Lock()
    admitted = asyncio.Event()
    resume = asyncio.Event()
    handler_admissions = 0
    commit_count = 0
    record_at_admission: dict[str, int] = {}
    record_at_commit_attempt: dict[str, int] = {}

    def read_record() -> dict[str, int]:
        # The coordinator cannot mutate until validation has admitted the handler.
        return dict(record)

    with tempfile.TemporaryDirectory() as temporary:
        audit = Path(temporary) / "audit.jsonl"
        store = MemoryStore()
        with guard(store=store, audit_path=audit):
            observed = observe(
                "synthetic-commit-window", adapter="mcp", name="read_record",
                reader=read_record, safe=True,
            )
            with reasoning("increment_record", depends_on=[observed]) as decision:
                decision_record = read_record()
                proposed_value = decision_record["value"] + 1

        server = MCPServer(
            "commit-window-demo",
            extensions=[FreshCtxMCPGuard(
                depends_on={"commit_record": [decision]}, store=store,
                protected_tools=["commit_record"], audit_path=audit,
            )],
        )

        @server.tool()
        async def commit_record() -> dict[str, str]:
            """Apply the previously justified increment after handler admission."""
            nonlocal handler_admissions, commit_count
            nonlocal record_at_admission, record_at_commit_attempt
            async with lock:
                handler_admissions += 1
                record_at_admission = dict(record)
            # This barrier is INSIDE the handler, after the real guard admitted it.
            admitted.set()
            await asyncio.wait_for(resume.wait(), timeout=WAIT_SECONDS)
            async with lock:
                record_at_commit_attempt = dict(record)
                if check_version and record["version"] != decision_record["version"]:
                    return {"status": "application_conflict"}
                # Compare and commit share the mutation lock, with no intervening await.
                record.update(version=record["version"] + 1, value=proposed_value)
                commit_count += 1
                return {"status": "committed"}

        async def coordinate():
            async with Client(server) as client:
                call = asyncio.create_task(client.call_tool("commit_record", {}))
                try:
                    await asyncio.wait_for(admitted.wait(), timeout=WAIT_SECONDS)
                    async with lock:
                        if mutate_after_admission:
                            record.update(version=record["version"] + 1, value=100)
                    resume.set()
                    return await asyncio.wait_for(call, timeout=WAIT_SECONDS)
                finally:
                    # Unblock the handler and drain the client call on errors/cancellation.
                    call.cancel()
                    resume.set()
                    await asyncio.wait_for(
                        asyncio.gather(call, return_exceptions=True), timeout=WAIT_SECONDS,
                    )

        # Also bound client startup and shutdown, beyond the two event waits.
        result = await asyncio.wait_for(coordinate(), timeout=4 * WAIT_SECONDS)
        return {
            "mutate_after_admission": mutate_after_admission,
            "check_version": check_version,
            "handler_admissions": handler_admissions,
            "commit_count": commit_count,
            "mcp_error": result.is_error,
            "application_result": result.structured_content["status"],
            "decision": decision_record,
            "record_at_admission": record_at_admission,
            "record_at_commit_attempt": record_at_commit_attempt,
            "record": dict(record),
        }


async def run_demo() -> list[dict[str, object]]:
    """Run independent rows sequentially, without timing-based sleeps."""
    return [
        await run_case(mutate, check)
        for mutate in (False, True)
        for check in (False, True)
    ]


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_demo()), indent=2))
