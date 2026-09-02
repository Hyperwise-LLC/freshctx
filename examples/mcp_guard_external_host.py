"""Validate FreshCtx MCP Guard across an out-of-process stdio boundary."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


ROOT = Path(__file__).resolve().parent
SCENARIOS = ("current", "stale", "unverifiable")


async def run_external_host(scenario: str) -> dict[str, object]:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    environment = dict(os.environ)
    environment["FRESHCTX_MCP_DEMO_SCENARIO"] = scenario
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "mcp_guard_stdio_server.py")],
        env=environment,
        cwd=ROOT,
    )
    async with Client(server) as client:
        tools = await client.list_tools()
        await client.call_tool("read_status", {})
        if scenario == "unverifiable":
            result = await client.call_tool("approve_refund", {"refund_id": "refund-117"})
        else:
            result = await client.call_tool(
                "transfer_money",
                {"amount": 900000, "beneficiary": "account-8832"},
            )
        execution_log = await client.call_tool("read_execution_log", {})
    return {
        "scenario": scenario,
        "transport": "stdio-subprocess",
        "tools": sorted(tool.name for tool in tools.tools),
        "mcp_error": result.is_error,
        "freshctx_state": (
            result.structured_content.get("state")
            if result.is_error and result.structured_content
            else "CURRENT"
        ),
        "executed": execution_log.structured_content["executed"],
    }


if __name__ == "__main__":
    print({scenario: asyncio.run(run_external_host(scenario)) for scenario in SCENARIOS})
