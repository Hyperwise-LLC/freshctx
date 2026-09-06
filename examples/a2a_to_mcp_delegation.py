"""Run a signed three-agent A2A delegation that ends at a guarded MCP tool."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import EventQueue
from mcp import Client
from mcp.server.mcpserver import MCPServer

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.a2a import (
    A2ADelegation,
    FreshCtxA2AExecutor,
    a2a_delegation_metadata,
    attest_a2a_delegation,
)
from freshctx.integrations.mcp_guard import FreshCtxMCPGuard


KEY = b"replace-with-a-process-local-key-of-32-bytes"


class Context:
    def __init__(self, metadata: dict[str, Any], task_id: str) -> None:
        self.metadata, self.task_id, self.context_id = metadata, task_id, "demo-context"


class Queue(EventQueue):
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


def envelope(delegation: A2ADelegation) -> dict[str, Any]:
    receipt = attest_a2a_delegation(delegation, issuer=delegation.origin_agent, key_id="demo", key=KEY)
    return a2a_delegation_metadata(delegation, receipt)


async def run_demo(scenario: str = "current") -> dict[str, Any]:
    if scenario not in {"current", "stale", "unverifiable"}:
        raise ValueError("scenario must be current, stale, or unverifiable")
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    state = root / "approval.txt"
    state.write_text("approved=true\n", encoding="utf-8")
    store = MemoryStore()
    audit = root / "audit.jsonl"
    with guard(store=store, audit_path=audit):
        token = observe(state)
        with reasoning("approve_action", depends_on=[token]) as decision:
            pass

    executed: list[str] = []
    server = MCPServer("a2a-mcp-demo", extensions=[FreshCtxMCPGuard(
        depends_on={"commit_action": [decision]}, store=store,
        protected_tools=["commit_action"], audit_path=audit)])

    @server.tool()
    def commit_action() -> dict[str, str]:
        executed.append("commit_action")
        return {"status": "committed"}

    if scenario == "stale":
        state.write_text("approved=false\n", encoding="utf-8")

    class FinalAgent(AgentExecutor):
        async def execute(self, context: Any, event_queue: EventQueue) -> None:
            del context, event_queue
            async with Client(server) as client:
                self.result = await client.call_tool("commit_action", {})

        async def cancel(self, context: Any, event_queue: EventQueue) -> None:
            del context, event_queue

    final = FinalAgent()
    dependencies = ["missing"] if scenario == "unverifiable" else [decision]
    final_guard = FreshCtxA2AExecutor(final, receiving_agent="executor", depends_on=dependencies,
                                      store=store, key_resolver=lambda issuer, key_id: KEY, audit_path=str(audit))

    second = A2ADelegation.create(root_correlation_id="demo-root", origin_agent="specialist",
                                  receiving_agent="executor", skill_id="commit_action",
                                  observation_ids=[token.id], ttl_seconds=60, parent_delegation_id="planner-hop")

    class Specialist(AgentExecutor):
        async def execute(self, context: Any, event_queue: EventQueue) -> None:
            del context
            await final_guard.execute(Context(envelope(second), "executor-task"), event_queue)

        async def cancel(self, context: Any, event_queue: EventQueue) -> None:
            del context, event_queue

    specialist_guard = FreshCtxA2AExecutor(
        Specialist(), receiving_agent="specialist", depends_on=[decision], store=store,
        key_resolver=lambda issuer, key_id: KEY, audit_path=str(audit))
    first = A2ADelegation.create(root_correlation_id="demo-root", origin_agent="planner",
                                 receiving_agent="specialist", skill_id="prepare_action",
                                 observation_ids=[token.id], ttl_seconds=60)
    queue = Queue()
    await specialist_guard.execute(Context(envelope(first), "specialist-task"), queue)
    result = {
        "scenario": scenario,
        "delegation_chain": [first.delegation_id, second.delegation_id],
        "final_mcp_executions": len(executed),
        "blocked": len(executed) == 0,
    }
    temporary.cleanup()
    return result


if __name__ == "__main__":
    print({name: asyncio.run(run_demo(name)) for name in ("current", "stale", "unverifiable")})
