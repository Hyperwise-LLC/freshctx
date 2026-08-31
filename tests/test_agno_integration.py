from __future__ import annotations

import asyncio
import runpy
import tempfile
import unittest
from pathlib import Path

from agno.tools import tool
from agno.tools.function import FunctionCall

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.errors import ConfigurationError
from freshctx.integrations.agno import FreshCtxAgnoBlocked, agno_async_tool_hook, agno_tool_hook


ROOT = Path(__file__).resolve().parents[1]


class AgnoIntegrationTests(unittest.TestCase):
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

    def test_actual_agno_tool_is_blocked_before_side_effect(self):
        decision = self._decision()
        called: list[str] = []
        hook = agno_tool_hook(depends_on=[decision], store=self.store, audit_path=self.audit)

        @tool(tool_hooks=[hook])
        def write_record(value: str) -> str:
            called.append(value)
            return value

        self.source.write_text("version=2\n", encoding="utf-8")
        with self.assertRaises(FreshCtxAgnoBlocked) as raised:
            FunctionCall(function=write_record, arguments={"value": "write"}).execute()
        self.assertEqual(called, [])
        self.assertEqual(raised.exception.result.state.value, "STALE_REASONING")

    def test_actual_agno_tool_runs_when_dependency_is_current(self):
        decision = self._decision()
        called: list[str] = []
        hook = agno_tool_hook(depends_on=[decision], store=self.store, audit_path=self.audit)

        @tool(tool_hooks=[hook])
        def write_record(value: str) -> str:
            called.append(value)
            return value

        result = FunctionCall(function=write_record, arguments={"value": "write"}).execute()

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result, "write")
        self.assertEqual(called, ["write"])

    def test_async_agno_tool_is_blocked_before_side_effect(self):
        async def scenario():
            decision = self._decision()
            called: list[str] = []
            hook = agno_async_tool_hook(depends_on=[decision], store=self.store, audit_path=self.audit)

            @tool(tool_hooks=[hook])
            async def write_record(value: str) -> str:
                called.append(value)
                return value

            self.source.write_text("version=2\n", encoding="utf-8")
            with self.assertRaises(FreshCtxAgnoBlocked) as raised:
                await FunctionCall(function=write_record, arguments={"value": "write"}).aexecute()
            return raised.exception, called

        blocked, called = asyncio.run(scenario())
        self.assertEqual(called, [])
        self.assertEqual(blocked.result.state.value, "STALE_REASONING")

    def test_empty_dependency_set_is_rejected_during_configuration(self):
        with self.assertRaises(ConfigurationError):
            agno_tool_hook(depends_on=[], store=self.store, audit_path=self.audit)

    def test_bounded_example_uses_real_agno_hook_chain(self):
        module = runpy.run_path(ROOT / "examples" / "agno_stale_tool.py")
        blocked = module["run_demo"]()
        current = module["run_demo"](change_source=False)
        self.assertEqual(blocked["agno_status"], "blocked")
        self.assertEqual(blocked["freshctx_state"], "STALE_REASONING")
        self.assertEqual(blocked["executed"], [])
        self.assertEqual(current["agno_status"], "success")
        self.assertEqual(current["executed"], ["staging"])


if __name__ == "__main__":
    unittest.main()
