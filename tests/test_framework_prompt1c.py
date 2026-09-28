"""Focused Prompt 1C adapter propagation checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from freshctx import ActionAttempt, FreshnessBlocked, MemoryStore, ProtectedParameter, guard, observe, parameter_digest, reasoning
from freshctx.integrations.langgraph import langgraph_action_node
from freshctx.integrations.agno import agno_tool_hook


class FrameworkPrompt1CTests(unittest.TestCase):
    def test_agno_capture_records_real_result_with_declared_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("account=123", encoding="utf-8")
            store = MemoryStore()
            audit = Path(directory) / "audit.jsonl"
            with guard(store=store, audit_path=audit):
                token = observe(source)
            outputs = []
            hook = agno_tool_hook(
                depends_on=[token], store=store, audit_path=audit,
                output_lineage=lambda name, arguments, result: ("lookup-1", [token]),
                on_output_node=outputs.append,
            )
            self.assertEqual(hook("lookup", lambda **values: values["account"], {"account": "123"}), "123")
            self.assertEqual(store.get(outputs[0].id).dependencies, (token.id,))
            self.assertEqual(store.get(outputs[0].id).metadata["output_digest"], parameter_digest("123"))

    def test_langgraph_captures_two_tool_outputs_for_parameter_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("account=123", encoding="utf-8")
            audit = Path(directory) / "audit.jsonl"
            store = MemoryStore()
            with guard(store=store, audit_path=audit):
                token = observe(source)
            outputs = []
            tool_a = langgraph_action_node(
                lambda state: {"account": "123"}, depends_on=[token], store=store,
                audit_path=audit, output_lineage=lambda state, result: ("tool-a-1", [token]),
                on_output_node=outputs.append,
            )
            first = tool_a({})
            tool_b = langgraph_action_node(
                lambda state: state["input"]["account"], depends_on=[outputs[-1]], store=store,
                audit_path=audit, output_lineage=lambda state, result: ("tool-b-1", [outputs[0]]),
                on_output_node=outputs.append,
            )
            value = tool_b({"input": first})
            called = []
            action = langgraph_action_node(
                lambda state: called.append(state["account"]), depends_on=[outputs[-1]], store=store,
                audit_path=audit,
                protected_parameters={"account": ProtectedParameter((outputs[-1].id,), parameter_digest(value))},
                parameter_values=lambda state: {"account": state["account"]},
            )
            action({"account": value})
            self.assertEqual(called, ["123"])
            self.assertEqual(store.get(outputs[1].id).dependencies, (outputs[0].id,))
            self.assertEqual(store.get(outputs[0].id).dependencies, (token.id,))
            source.write_text("account=999", encoding="utf-8")
            with self.assertRaises(FreshnessBlocked) as raised:
                action({"account": value})
            self.assertEqual(raised.exception.result.state.value, "STALE_REASONING")
            self.assertEqual(called, ["123"])

    def test_langgraph_protected_parameter_and_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("account=123", encoding="utf-8")
            audit = Path(directory) / "audit.jsonl"
            store = MemoryStore()
            with guard(store=store, audit_path=audit):
                token = observe(source)
                with reasoning("tool_output", depends_on=[token], metadata={"tool_invocation_id": "lookup-1", "output_digest": parameter_digest("123")}) as output:
                    pass
            called = []
            protected = langgraph_action_node(
                lambda state: called.append(state["account"]),
                depends_on=[output], store=store, audit_path=audit,
                protected_parameters={"account": ProtectedParameter((output.id,), parameter_digest("123"))},
                parameter_values=lambda state: {"account": state["account"]},
                action_attempt=lambda state: ActionAttempt(state["operation_id"], state["attempt_id"]),
            )
            protected({"account": "123", "operation_id": "op-1", "attempt_id": "try-1"})
            self.assertEqual(called, ["123"])
            source.write_text("account=999", encoding="utf-8")
            with self.assertRaises(FreshnessBlocked) as raised:
                protected({"account": "123", "operation_id": "op-1", "attempt_id": "try-2"})
            self.assertEqual(raised.exception.result.state.value, "STALE_REASONING")
            self.assertEqual(called, ["123"])

    def test_langgraph_missing_actual_parameter_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("account=123", encoding="utf-8")
            store = MemoryStore()
            with guard(store=store, audit_path=Path(directory) / "audit.jsonl"):
                token = observe(source)
            called = []
            protected = langgraph_action_node(
                lambda state: called.append(state), depends_on=[token], store=store,
                audit_path=Path(directory) / "audit.jsonl",
                protected_parameters={"account": ProtectedParameter((token.id,), parameter_digest("123"))},
            )
            with self.assertRaises(FreshnessBlocked) as raised:
                protected({"account": "123"})
            self.assertEqual(raised.exception.result.state.value, "UNVERIFIABLE")
            self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
