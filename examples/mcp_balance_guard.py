"""Run a real in-process MCP tool call through FreshCtx MCP Guard.

Install with: python -m pip install 'freshctx[mcp-guard]'
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from mcp import Client
from mcp.server.mcpserver import MCPServer

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.mcp_guard import FreshCtxMCPGuard


async def run_demo(*, change_balance: bool = True) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        balance = root / "balance.txt"
        balance.write_text("available_balance=5200000\n", encoding="utf-8")
        audit = root / "mcp-guard-audit.jsonl"
        store = MemoryStore()

        with guard(store=store, audit_path=audit):
            observed_balance = observe(balance)
            with reasoning("approve_transfer", depends_on=[observed_balance]) as approval:
                pass

        executed: list[int] = []
        server = MCPServer(
            "treasury-demo",
            extensions=[
                FreshCtxMCPGuard(
                    depends_on={"transfer_money": [approval]},
                    store=store,
                    protected_tools=["transfer_money"],
                    audit_path=audit,
                )
            ],
        )

        @server.tool()
        def transfer_money(amount: int, beneficiary: str) -> dict[str, object]:
            """Transfer money after the application approves it."""
            del beneficiary
            executed.append(amount)
            return {"status": "transferred", "amount": amount}

        if change_balance:
            balance.write_text("available_balance=600000\n", encoding="utf-8")

        async with Client(server) as client:
            result = await client.call_tool(
                "transfer_money",
                {"amount": 900000, "beneficiary": "account-8832"},
            )

        return {
            "mcp_error": result.is_error,
            "freshctx_state": (
                result.structured_content.get("state")
                if result.is_error and result.structured_content
                else "CURRENT"
            ),
            "executed": executed,
        }


if __name__ == "__main__":
    blocked = asyncio.run(run_demo())
    current = asyncio.run(run_demo(change_balance=False))
    print({"changed_balance": blocked, "unchanged_balance": current})
