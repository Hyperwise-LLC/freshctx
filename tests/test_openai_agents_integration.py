from __future__ import annotations

import asyncio
import runpy
import tempfile
import unittest
from pathlib import Path

from agents import Agent, Runner, function_tool
from agents.exceptions import ToolInputGuardrailTripwireTriggered
from agents.testing import ScriptedModel, assistant_message, function_call

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.errors import ConfigurationError
from freshctx.integrations.openai_agents import openai_agents_tool_guardrail


ROOT = Path(__file__).resolve().parents[1]


class OpenAIAgentsIntegrationTests(unittest.TestCase):
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

    def test_real_function_tool_runs_once_when_current(self):
        decision = self._decision()
        called: list[str] = []
        freshness = openai_agents_tool_guardrail(
            depends_on=[decision], store=self.store, audit_path=self.audit
        )

        @function_tool(tool_input_guardrails=[freshness])
        def write_record(value: str) -> str:
            """Write one bounded record."""
            called.append(value)
            return value

        model = ScriptedModel(
            [
                [function_call("write_record", {"value": "write"}, call_id="call-freshctx-123")],
                [assistant_message("complete")],
            ]
        )
        result = asyncio.run(Runner.run(Agent(name="bounded-test", model=model, tools=[write_record]), "write"))
        self.assertEqual(result.final_output, "complete")
        self.assertEqual(called, ["write"])

    def test_real_function_tool_tripwire_blocks_stale_action(self):
        decision = self._decision()
        called: list[str] = []
        freshness = openai_agents_tool_guardrail(
            depends_on=[decision], store=self.store, audit_path=self.audit
        )

        @function_tool(tool_input_guardrails=[freshness])
        async def write_record(value: str) -> str:
            """Write one bounded record."""
            called.append(value)
            return value

        self.source.write_text("version=2\n", encoding="utf-8")
        with self.assertRaises(ToolInputGuardrailTripwireTriggered) as raised:
            model = ScriptedModel(
                [[function_call("write_record", {"value": "sensitive-business-value"}, call_id="call-freshctx-123")]]
            )
            asyncio.run(Runner.run(Agent(name="bounded-test", model=model, tools=[write_record]), "write"))

        self.assertEqual(called, [])
        result = raised.exception.output.output_info["freshctx"]
        self.assertEqual(result["state"], "STALE_REASONING")
        self.assertEqual(result["policy_decision"], "block")
        self.assertNotIn("sensitive-business-value", repr(self.store.objects))
        self.assertNotIn("sensitive-business-value", self.audit.read_text(encoding="utf-8"))
        self.assertIn('"run_id": "call-freshctx-123"', self.audit.read_text(encoding="utf-8"))

    def test_empty_dependency_set_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            openai_agents_tool_guardrail(depends_on=[], store=self.store, audit_path=self.audit)

    def test_bounded_example_uses_real_sdk_tool_pipeline(self):
        module = runpy.run_path(ROOT / "examples" / "openai_agents_stale_tool.py")
        blocked = module["run_demo"]()
        current = module["run_demo"](change_source=False)
        self.assertEqual(blocked["sdk_status"], "blocked")
        self.assertEqual(blocked["freshctx_state"], "STALE_REASONING")
        self.assertEqual(blocked["executed"], [])
        self.assertEqual(current["sdk_status"], "success")
        self.assertEqual(current["executed"], ["staging"])


if __name__ == "__main__":
    unittest.main()
