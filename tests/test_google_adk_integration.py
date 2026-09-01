from __future__ import annotations

import asyncio
import runpy
import tempfile
import unittest
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.errors import ConfigurationError
from freshctx.integrations.google_adk import google_adk_tool_callback


ROOT = Path(__file__).resolve().parents[1]


class ScriptedToolModel(BaseLlm):
    tool_name: str
    arguments: dict[str, Any]
    calls: int = 0

    async def generate_content_async(self, llm_request: Any, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=self.tool_name,
                                args=self.arguments,
                                id="adk-call-123",
                            )
                        )
                    ],
                )
            )
        else:
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="complete")]))


class GoogleADKIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "state.txt"
        self.source.write_text("version=1\n", encoding="utf-8")
        self.store = MemoryStore()
        self.audit = self.root / "audit.jsonl"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _decision(self):
        with guard(store=self.store, audit_path=self.audit):
            token = observe(self.source)
            with reasoning("choose_action", depends_on=[token]) as decision:
                pass
        return decision

    async def _run_agent(self, tool: Any, callback: Any, arguments: dict[str, Any]):
        model = ScriptedToolModel(model="scripted", tool_name="write_record", arguments=arguments)
        agent = Agent(
            name="bounded_test",
            model=model,
            tools=[tool],
            before_tool_callback=callback,
        )
        return await InMemoryRunner(agent=agent).run_debug("write", quiet=True)

    @staticmethod
    def _tool_response(events: list[Any]) -> dict[str, Any]:
        return next(
            part.function_response.response
            for event in events
            if event.content
            for part in event.content.parts
            if part.function_response
        )

    def test_real_sync_tool_runs_once_when_current(self):
        decision = self._decision()
        called: list[str] = []

        def write_record(value: str) -> dict[str, str]:
            """Write one bounded record."""
            called.append(value)
            return {"status": "written", "value": value}

        callback = google_adk_tool_callback(depends_on=[decision], store=self.store, audit_path=self.audit)
        events = asyncio.run(self._run_agent(write_record, callback, {"value": "write"}))
        self.assertEqual(called, ["write"])
        self.assertEqual(self._tool_response(events)["status"], "written")

    def test_real_async_tool_is_skipped_when_stale(self):
        decision = self._decision()
        called: list[str] = []

        async def write_record(value: str) -> dict[str, str]:
            """Write one bounded record."""
            called.append(value)
            return {"status": "written", "value": value}

        callback = google_adk_tool_callback(depends_on=[decision], store=self.store, audit_path=self.audit)
        self.source.write_text("version=2\n", encoding="utf-8")
        events = asyncio.run(
            self._run_agent(write_record, callback, {"value": "sensitive-business-value"})
        )

        response = self._tool_response(events)
        self.assertEqual(called, [])
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["freshctx"]["state"], "STALE_REASONING")
        self.assertEqual(response["freshctx"]["policy_decision"], "block")
        self.assertNotIn("sensitive-business-value", repr(self.store.objects))
        self.assertNotIn("sensitive-business-value", self.audit.read_text(encoding="utf-8"))
        self.assertIn('"run_id": "adk-call-123"', self.audit.read_text(encoding="utf-8"))

    def test_dynamic_dependencies_and_tool_filter(self):
        decision = self._decision()
        resolved: list[str] = []

        def resolver(tool: Any, tool_context: Any):
            resolved.append(f"{tool.name}:{tool_context.function_call_id}")
            return [decision]

        callback = google_adk_tool_callback(
            depends_on=resolver,
            store=self.store,
            tool_names=["write_record"],
            audit_path=self.audit,
        )
        tool = type("Tool", (), {"name": "unprotected"})()
        context = type("Context", (), {"function_call_id": "ignored"})()
        result = asyncio.run(callback(tool=tool, args={"secret": "value"}, tool_context=context))
        self.assertIsNone(result)
        self.assertEqual(resolved, [])

    def test_unverifiable_dependency_uses_native_blocked_response(self):
        called: list[str] = []

        def write_record(value: str) -> dict[str, str]:
            """Write one bounded record."""
            called.append(value)
            return {"status": "written", "value": value}

        callback = google_adk_tool_callback(
            depends_on=["missing-dependency"],
            store=self.store,
            audit_path=self.audit,
        )
        events = asyncio.run(self._run_agent(write_record, callback, {"value": "write"}))
        response = self._tool_response(events)
        self.assertEqual(called, [])
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["freshctx"]["state"], "UNVERIFIABLE")
        self.assertEqual(response["freshctx"]["policy_decision"], "block")

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            google_adk_tool_callback(depends_on=[], store=self.store)
        with self.assertRaises(ConfigurationError):
            google_adk_tool_callback(depends_on=["decision"], store=self.store, tool_names=[])

    def test_bounded_example_uses_real_adk_tool_pipeline(self):
        module = runpy.run_path(ROOT / "examples" / "google_adk_stale_tool.py")
        blocked = module["run_demo"]()
        current = module["run_demo"](change_source=False)
        self.assertEqual(blocked["adk_status"], "blocked")
        self.assertEqual(blocked["freshctx_state"], "STALE_REASONING")
        self.assertEqual(blocked["executed"], [])
        self.assertEqual(current["adk_status"], "deployed")
        self.assertEqual(current["freshctx_state"], "CURRENT")
        self.assertEqual(current["executed"], ["staging"])


if __name__ == "__main__":
    unittest.main()
