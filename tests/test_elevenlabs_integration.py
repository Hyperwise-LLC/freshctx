from __future__ import annotations

import asyncio
import runpy
import tempfile
import unittest
from pathlib import Path

from elevenlabs.conversational_ai.conversation import ClientTools

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.errors import ConfigurationError
from freshctx.integrations.elevenlabs import register_elevenlabs_client_tool


ROOT = Path(__file__).resolve().parents[1]


class ElevenLabsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "customer.txt"
        self.source.write_text("Ada Lovelace\n", encoding="utf-8")
        self.store = MemoryStore()
        self.audit = self.root / "audit.jsonl"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def decision(self):
        with guard(store=self.store, audit_path=self.audit):
            source = observe(self.source)
            with reasoning("voice_customer", depends_on=[source]) as decision:
                pass
        return decision

    def test_real_client_tools_runs_current_handler_once(self):
        called: list[str] = []
        tools = ClientTools()
        register_elevenlabs_client_tool(
            tools,
            "confirm_booking",
            lambda parameters: called.append(parameters["booking_id"]) or {"status": "confirmed"},
            depends_on=[self.decision()],
            store=self.store,
            audit_path=self.audit,
        )
        result = asyncio.run(tools.handle("confirm_booking", {"booking_id": "B-1"}))
        self.assertEqual(result, {"status": "confirmed"})
        self.assertEqual(called, ["B-1"])

    def test_real_client_tools_blocks_stale_handler(self):
        called: list[str] = []
        decision = self.decision()
        self.source.write_text("Augusta Ada King\n", encoding="utf-8")
        tools = ClientTools()
        register_elevenlabs_client_tool(
            tools,
            "confirm_booking",
            lambda parameters: called.append(parameters["booking_id"]),
            depends_on=[decision],
            store=self.store,
            audit_path=self.audit,
        )
        result = asyncio.run(tools.handle("confirm_booking", {"booking_id": "B-1"}))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["freshctx"]["state"], "STALE_REASONING")
        self.assertEqual(result["correlation"]["runtime"], "elevenlabs")
        self.assertEqual(called, [])

    def test_unverifiable_dependency_blocks_and_arguments_are_not_persisted(self):
        called: list[str] = []
        tools = ClientTools()
        register_elevenlabs_client_tool(
            tools,
            "update_account",
            lambda parameters: called.append(parameters["secret"]),
            depends_on=["unresolved-voice-match"],
            store=self.store,
            audit_path=self.audit,
        )
        result = asyncio.run(tools.handle("update_account", {"secret": "voice-secret-9f6d"}))
        self.assertEqual(result["freshctx"]["state"], "UNVERIFIABLE")
        self.assertEqual(result["correlation"]["freshness_state"], "UNVERIFIABLE")
        self.assertEqual(called, [])
        self.assertNotIn("voice-secret-9f6d", repr(self.store.objects))
        self.assertNotIn("voice-secret-9f6d", self.audit.read_text(encoding="utf-8"))

    def test_async_client_tool_is_blocked_before_handler(self):
        called: list[str] = []
        decision = self.decision()
        self.source.write_text("changed\n", encoding="utf-8")
        tools = ClientTools()

        async def update_account(parameters):
            called.append(parameters["account_id"])

        register_elevenlabs_client_tool(
            tools,
            "update_account",
            update_account,
            depends_on=[decision],
            store=self.store,
            audit_path=self.audit,
            is_async=True,
        )
        result = asyncio.run(tools.handle("update_account", {"account_id": "A-1"}))
        self.assertEqual(result["freshctx"]["state"], "STALE_REASONING")
        self.assertEqual(called, [])

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            register_elevenlabs_client_tool(
                ClientTools(), "", lambda parameters: parameters,
                depends_on=[], store=self.store,
            )

    def test_bounded_voice_example_uses_real_client_tool_registry(self):
        module = runpy.run_path(ROOT / "examples" / "elevenlabs_voice_customer_guard.py")
        results = module["run_demo"]()
        self.assertEqual(results[0]["executions"], ["booking-sensitive-4471"])
        self.assertEqual(results[1]["response"]["freshctx"]["state"], "STALE_REASONING")
        self.assertEqual(results[2]["response"]["freshctx"]["state"], "UNVERIFIABLE")
        self.assertEqual(results[1]["executions"], [])
        self.assertEqual(results[2]["executions"], [])


if __name__ == "__main__":
    unittest.main()
