from __future__ import annotations

import asyncio
import runpy
import tempfile
import unittest
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning
from freshctx.errors import ConfigurationError
from freshctx.integrations.langgraph import langgraph_async_action_node
from freshctx.integrations.langgraph import langgraph_action_node


ROOT = Path(__file__).resolve().parents[1]


class AsyncActionState(TypedDict):
    value: str
    decision: Any
    execution_id: str
    completed: bool


class LangGraphIntegrationTests(unittest.TestCase):
    def test_stale_config_blocks_action_node(self):
        module = runpy.run_path(ROOT / "examples" / "langgraph_stale_config.py")
        self.assertTrue(module["run_demo"]())

    def test_current_config_runs_action_node_once(self):
        module = runpy.run_path(ROOT / "examples" / "langgraph_stale_config.py")
        self.assertTrue(module["run_demo"](change_source=False))

    def test_async_graph_blocks_before_action_body(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "state.txt"
                source.write_text("version=1\n", encoding="utf-8")
                store = MemoryStore()
                audit = root / "audit.jsonl"
                executed = []

                with guard(store=store, audit_path=audit):
                    token = observe(source)
                    with reasoning("choose_action", depends_on=[token]) as decision:
                        pass

                async def action(state):
                    executed.append(state["value"])
                    return {"completed": True}

                protected = langgraph_async_action_node(
                    action,
                    depends_on=lambda state: [state["decision"]],
                    store=store,
                    action_name="write",
                    execution_id=lambda state: state["execution_id"],
                    audit_path=audit,
                )

                builder = StateGraph(AsyncActionState)
                builder.add_node("write", protected)
                builder.add_edge(START, "write")
                builder.add_edge("write", END)
                source.write_text("version=2\n", encoding="utf-8")

                with self.assertRaises(FreshnessBlocked) as raised:
                    await builder.compile().ainvoke(
                        {
                            "value": "side-effect",
                            "decision": decision,
                            "execution_id": "async-run",
                            "completed": False,
                        }
                    )
                return raised.exception, executed

        blocked, executed = asyncio.run(scenario())
        self.assertEqual(blocked.result.state.value, "STALE_REASONING")
        self.assertEqual(executed, [])

    def test_state_resolver_and_execution_id_are_recorded_without_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state.txt"
            source.write_text("version=1\n", encoding="utf-8")
            store = MemoryStore()
            audit = root / "audit.jsonl"
            with guard(store=store, audit_path=audit):
                token = observe(source)
                with reasoning("choose_action", depends_on=[token]) as decision:
                    pass

            protected = langgraph_action_node(
                lambda state: {"completed": state["payload"] == "secret-business-value"},
                depends_on=lambda state: [state["decision"]],
                store=store,
                action_name="write_record",
                execution_id=lambda state: state["execution_id"],
                audit_path=audit,
            )
            result = protected(
                {
                    "decision": decision,
                    "execution_id": "langgraph-run-123",
                    "payload": "secret-business-value",
                }
            )

            self.assertTrue(result["completed"])
            integration_nodes = [
                value
                for value in store.objects.values()
                if getattr(value, "kind", None) == "pre_action_integration"
            ]
            self.assertEqual(len(integration_nodes), 1)
            self.assertEqual(integration_nodes[0].metadata["runtime"], "langgraph")
            self.assertEqual(integration_nodes[0].metadata["action"], "write_record")
            self.assertNotIn("secret-business-value", repr(integration_nodes[0]))
            self.assertIn('"run_id": "langgraph-run-123"', audit.read_text(encoding="utf-8"))

    def test_invalid_state_mapping_fails_before_action(self):
        executed = []
        protected = langgraph_action_node(
            lambda state: executed.append(state),
            depends_on=lambda _state: [],
            store=MemoryStore(),
        )
        with self.assertRaises(ConfigurationError):
            protected({})
        self.assertEqual(executed, [])


if __name__ == "__main__":
    unittest.main()
