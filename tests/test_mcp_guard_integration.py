from __future__ import annotations

import asyncio
import importlib.metadata
import runpy
import tempfile
import unittest
from pathlib import Path

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.errors import ConfigurationError


try:
    MCP_V2 = int(importlib.metadata.version("mcp").split(".", 1)[0]) >= 2
except importlib.metadata.PackageNotFoundError:
    MCP_V2 = False

if MCP_V2:
    from mcp import Client
    from mcp.server.mcpserver import MCPServer

    from freshctx.integrations.mcp_guard import FreshCtxMCPGuard


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(MCP_V2, "official MCP Python SDK v2 is not installed")
class MCPGuardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "balance.txt"
        self.source.write_text("balance=5200000\n", encoding="utf-8")
        self.store = MemoryStore()
        self.audit = self.root / "mcp-audit.jsonl"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _decision(self):
        with guard(store=self.store, audit_path=self.audit):
            token = observe(self.source)
            with reasoning("approve_transfer", depends_on=[token]) as decision:
                pass
        return decision

    async def _call(self, *, change_source: bool = False, secret: str = "acct-secret"):
        decision = self._decision()
        executed: list[tuple[int, str]] = []
        extension = FreshCtxMCPGuard(
            depends_on={"transfer_money": [decision]},
            store=self.store,
            protected_tools=["transfer_money"],
            audit_path=self.audit,
        )
        server = MCPServer("freshctx-test", extensions=[extension])

        @server.tool()
        def transfer_money(amount: int, beneficiary: str) -> dict[str, object]:
            """Transfer money to a beneficiary."""
            executed.append((amount, beneficiary))
            return {"status": "transferred", "amount": amount}

        if change_source:
            self.source.write_text("balance=600000\n", encoding="utf-8")

        async with Client(server) as client:
            result = await client.call_tool(
                "transfer_money",
                {"amount": 900000, "beneficiary": secret},
            )
        return result, executed

    def test_current_evidence_executes_real_mcp_tool_once(self):
        result, executed = asyncio.run(self._call())
        self.assertFalse(result.is_error)
        self.assertEqual(executed, [(900000, "acct-secret")])

    def test_stale_evidence_returns_native_tool_error_without_execution(self):
        result, executed = asyncio.run(self._call(change_source=True, secret="private-beneficiary"))
        self.assertTrue(result.is_error)
        self.assertEqual(executed, [])
        self.assertEqual(result.structured_content["status"], "blocked")
        self.assertEqual(result.structured_content["state"], "STALE_REASONING")
        self.assertEqual(result.meta["com.freshctx/result"]["policy_decision"], "block")
        self.assertNotIn("private-beneficiary", self.audit.read_text(encoding="utf-8"))
        self.assertNotIn("private-beneficiary", repr(self.store.objects))
        integration_nodes = [
            value
            for value in self.store.objects.values()
            if getattr(value, "kind", None) == "pre_action_integration"
        ]
        self.assertEqual(len(integration_nodes), 1)
        self.assertEqual(integration_nodes[0].metadata["runtime"], "mcp")
        self.assertEqual(integration_nodes[0].metadata["action"], "transfer_money")

    def test_unverifiable_dependency_fails_closed(self):
        async def run():
            executed: list[bool] = []
            server = MCPServer(
                "freshctx-test",
                extensions=[
                    FreshCtxMCPGuard(
                        depends_on={"write": ["missing-dependency"]},
                        store=self.store,
                        audit_path=self.audit,
                    )
                ],
            )

            @server.tool()
            def write() -> str:
                executed.append(True)
                return "written"

            async with Client(server) as client:
                result = await client.call_tool("write", {})
            return result, executed

        result, executed = asyncio.run(run())
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["state"], "UNVERIFIABLE")
        self.assertEqual(executed, [])

    def test_unselected_tool_passes_without_dependency_resolution(self):
        resolved: list[str] = []

        def resolver(tool_name: str):
            resolved.append(tool_name)
            return ["missing"]

        async def run():
            server = MCPServer(
                "freshctx-test",
                extensions=[
                    FreshCtxMCPGuard(
                        depends_on=resolver,
                        store=self.store,
                        protected_tools=["protected"],
                        audit_path=self.audit,
                    )
                ],
            )

            @server.tool()
            def public() -> str:
                return "ok"

            async with Client(server) as client:
                return await client.call_tool("public", {})

        result = asyncio.run(run())
        self.assertFalse(result.is_error)
        self.assertEqual(resolved, [])

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            FreshCtxMCPGuard(depends_on={}, store=self.store)
        with self.assertRaises(ConfigurationError):
            FreshCtxMCPGuard(depends_on=["decision"], store=None)
        with self.assertRaises(ConfigurationError):
            FreshCtxMCPGuard(depends_on=["decision"], store=self.store, protected_tools=[])

    def test_bounded_example_runs_through_real_mcp_server(self):
        module = runpy.run_path(ROOT / "examples" / "mcp_balance_guard.py")
        blocked = asyncio.run(module["run_demo"]())
        current = asyncio.run(module["run_demo"](change_balance=False))
        self.assertTrue(blocked["mcp_error"])
        self.assertEqual(blocked["freshctx_state"], "STALE_REASONING")
        self.assertEqual(blocked["executed"], [])
        self.assertFalse(current["mcp_error"])
        self.assertEqual(current["executed"], [900000])


if __name__ == "__main__":
    unittest.main()
