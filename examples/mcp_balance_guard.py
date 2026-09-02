"""Demonstrate current, stale, and unverifiable MCP tool calls.

Install the public package with: python -m pip install 'freshctx[mcp-guard]==0.9.0'
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.server.mcpserver import MCPServer

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.mcp_guard import FreshCtxMCPGuard


SCENARIOS = frozenset({"current", "stale", "unverifiable"})


def build_demo_server(
    scenario: str,
) -> tuple[MCPServer[Any], tempfile.TemporaryDirectory[str], list[dict[str, object]]]:
    """Build a three-tool server with two independently protected actions."""

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {sorted(SCENARIOS)}")

    temporary_directory = tempfile.TemporaryDirectory()
    root = Path(temporary_directory.name)
    balance = root / "balance.txt"
    balance.write_text("available_balance=5200000\n", encoding="utf-8")
    audit = root / "mcp-guard-audit.jsonl"
    store = MemoryStore()
    eligibility = {"available": True, "status": "eligible"}

    def read_refund_eligibility() -> dict[str, str]:
        if not eligibility["available"]:
            raise ConnectionError("refund eligibility service unavailable")
        return {"status": str(eligibility["status"])}

    with guard(store=store, audit_path=audit):
        observed_balance = observe(balance)
        observed_eligibility = observe(
            "refund-eligibility-service",
            adapter="mcp",
            name="read_refund_eligibility",
            reader=read_refund_eligibility,
            safe=True,
        )
        with reasoning("approve_transfer", depends_on=[observed_balance]) as transfer_approval:
            pass
        with reasoning("approve_refund", depends_on=[observed_eligibility]) as refund_approval:
            pass

    executed: list[dict[str, object]] = []
    server = MCPServer(
        "treasury-demo",
        extensions=[
            FreshCtxMCPGuard(
                depends_on={
                    "transfer_money": [transfer_approval],
                    "approve_refund": [refund_approval],
                },
                store=store,
                protected_tools=["transfer_money", "approve_refund"],
                audit_path=audit,
            )
        ],
    )

    @server.tool()
    def read_status() -> dict[str, object]:
        """Return non-sensitive demo status without a FreshCtx guard."""
        return {"service": "treasury-demo", "executed_count": len(executed)}

    @server.tool()
    def read_execution_log() -> dict[str, object]:
        """Return the demo execution log without a FreshCtx guard."""
        return {"executed": list(executed)}

    @server.tool()
    def transfer_money(amount: int, beneficiary: str) -> dict[str, object]:
        """Transfer money after the application approves it."""
        del beneficiary
        executed.append({"tool": "transfer_money", "amount": amount})
        return {"status": "transferred", "amount": amount}

    @server.tool()
    def approve_refund(refund_id: str) -> dict[str, object]:
        """Approve a refund after the application checks eligibility."""
        executed.append({"tool": "approve_refund", "refund_id": refund_id})
        return {"status": "approved", "refund_id": refund_id}

    if scenario == "stale":
        balance.write_text("available_balance=600000\n", encoding="utf-8")
    elif scenario == "unverifiable":
        eligibility["available"] = False

    return server, temporary_directory, executed


async def run_demo(scenario: str) -> dict[str, object]:
    server, temporary_directory, executed = build_demo_server(scenario)
    try:
        async with Client(server) as client:
            status = await client.call_tool("read_status", {})
            if scenario == "unverifiable":
                result = await client.call_tool("approve_refund", {"refund_id": "refund-117"})
            else:
                result = await client.call_tool(
                    "transfer_money",
                    {"amount": 900000, "beneficiary": "account-8832"},
                )
        return {
            "scenario": scenario,
            "unprotected_status_error": status.is_error,
            "mcp_error": result.is_error,
            "freshctx_state": (
                result.structured_content.get("state")
                if result.is_error and result.structured_content
                else "CURRENT"
            ),
            "executed": list(executed),
        }
    finally:
        temporary_directory.cleanup()


if __name__ == "__main__":
    print({scenario: asyncio.run(run_demo(scenario)) for scenario in sorted(SCENARIOS)})
