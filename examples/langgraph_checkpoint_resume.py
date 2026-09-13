"""Reproduce revalidation after a persisted LangGraph interrupt.

The graph pauses before its protected action. The declared source changes while
the graph is paused. Resuming the same checkpoint reaches the real action path,
where FreshCtx revalidates the dependency and blocks before the action body.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning
from freshctx.integrations.langgraph import langgraph_action_node


class ActionState(TypedDict):
    decision: Any
    execution_id: str
    completed: bool


def run_demo() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "approval.txt"
        audit = root / "audit.jsonl"
        source.write_text("approved\n", encoding="utf-8")
        store = MemoryStore()
        executed: list[str] = []

        with guard(store=store, audit_path=audit):
            observation = observe(source)
            with reasoning("approve_action", depends_on=[observation]) as decision:
                pass

        def pause(state: ActionState) -> dict[str, bool]:
            interrupt("resume protected action")
            return {"completed": state["completed"]}

        def action(state: ActionState) -> dict[str, bool]:
            executed.append(state["execution_id"])
            return {"completed": True}

        protected = langgraph_action_node(
            action,
            depends_on=lambda state: [state["decision"]],
            store=store,
            action_name="write_after_resume",
            execution_id=lambda state: state["execution_id"],
            audit_path=audit,
        )
        builder = StateGraph(ActionState)
        builder.add_node("pause", pause)
        builder.add_node("write", protected)
        builder.add_edge(START, "pause")
        builder.add_edge("pause", "write")
        builder.add_edge("write", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "freshctx-checkpoint-demo"}}

        paused = graph.invoke(
            {
                "decision": decision.id,
                "execution_id": "checkpoint-run-1",
                "completed": False,
            },
            config,
        )
        source.write_text("revoked\n", encoding="utf-8")

        try:
            graph.invoke(Command(resume=True), config)
        except FreshnessBlocked as blocked:
            return {
                "paused_before_action": "__interrupt__" in paused,
                "source_changed_while_paused": True,
                "freshness": blocked.result.state.value,
                "policy_decision": blocked.result.policy_decision,
                "action_executions": len(executed),
                "execution_id": blocked.correlation.execution_id,
            }
        raise AssertionError("resumed stale reasoning should block before the action body")


if __name__ == "__main__":
    print(run_demo())
