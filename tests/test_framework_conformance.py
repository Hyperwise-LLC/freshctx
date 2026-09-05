from __future__ import annotations

import asyncio
import os
import unittest
from collections.abc import AsyncGenerator, Callable
from typing import Any, TypedDict

from freshctx import FreshnessBlocked

from tests.framework_conformance import (
    CONTRACT_VERSION,
    SENSITIVE_ARGUMENT,
    ConformanceFixture,
    ConformanceOutcome,
    outcome,
    read_audit_events,
)


SITUATIONS = ("current", "stale", "unverifiable", "unrelated_changed")
FRAMEWORK_RUNTIMES = ("agno", "langgraph", "openai_agents", "google_adk", "elevenlabs")
RUNTIMES = tuple(
    name.strip()
    for name in os.environ.get(
        "FRESHCTX_CONFORMANCE_RUNTIMES", ",".join(FRAMEWORK_RUNTIMES)
    ).split(",")
    if name.strip()
)

if "agno" in RUNTIMES:
    from agno.tools import tool
    from agno.tools.function import FunctionCall

    from freshctx.integrations.agno import FreshCtxAgnoBlocked, agno_async_tool_hook, agno_tool_hook

if "langgraph" in RUNTIMES:
    from langgraph.graph import END, START, StateGraph

    from freshctx.integrations.langgraph import langgraph_action_node

if "openai_agents" in RUNTIMES:
    from agents import Agent as OpenAIAgent
    from agents import Runner, function_tool
    from agents.exceptions import ToolInputGuardrailTripwireTriggered
    from agents.testing import ScriptedModel, assistant_message, function_call

    from freshctx.integrations.openai_agents import openai_agents_tool_guardrail

if "google_adk" in RUNTIMES:
    from google.adk.agents import Agent as GoogleAgent
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from freshctx.integrations.google_adk import google_adk_tool_callback
else:
    BaseLlm = object

if "elevenlabs" in RUNTIMES:
    from elevenlabs.conversational_ai.conversation import ClientTools

    from freshctx.integrations.elevenlabs import register_elevenlabs_client_tool

if "mcp" in RUNTIMES:
    from mcp import Client
    from mcp.server.mcpserver import MCPServer

    from freshctx.integrations.mcp_guard import FreshCtxMCPGuard


class GraphState(TypedDict):
    payload: str
    dependency: Any
    completed: bool


class ScriptedGoogleToolModel(BaseLlm):
    calls: int = 0

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="write_record",
                                args={"value": SENSITIVE_ARGUMENT},
                                id="adk-conformance-call",
                            )
                        )
                    ],
                )
            )
        else:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="complete")])
            )


def run_agno(fixture: ConformanceFixture) -> ConformanceOutcome:
    executed: list[str] = []
    hook = agno_tool_hook(
        depends_on=fixture.dependencies,
        store=fixture.store,
        audit_path=fixture.audit_path,
    )

    @tool(tool_hooks=[hook])
    def write_record(value: str) -> str:
        executed.append(value)
        return value

    try:
        FunctionCall(
            function=write_record,
            arguments={"value": SENSITIVE_ARGUMENT},
        ).execute()
    except FreshCtxAgnoBlocked as blocked:
        return outcome(
            fixture,
            runtime="agno",
            state=blocked.result.state.value,
            policy_decision=blocked.result.policy_decision,
            executions=len(executed),
        )
    return outcome(
        fixture,
        runtime="agno",
        state="CURRENT",
        policy_decision="allow",
        executions=len(executed),
    )


def run_langgraph(fixture: ConformanceFixture) -> ConformanceOutcome:
    executed: list[str] = []

    def write_record(state: GraphState) -> dict[str, bool]:
        executed.append(state["payload"])
        return {"completed": True}

    protected = langgraph_action_node(
        write_record,
        depends_on=lambda state: state["dependency"],
        store=fixture.store,
        action_name="write_record",
        audit_path=fixture.audit_path,
    )
    builder = StateGraph(GraphState)
    builder.add_node("write_record", protected)
    builder.add_edge(START, "write_record")
    builder.add_edge("write_record", END)
    try:
        builder.compile().invoke(
            {
                "payload": SENSITIVE_ARGUMENT,
                "dependency": fixture.dependencies,
                "completed": False,
            }
        )
    except FreshnessBlocked as blocked:
        return outcome(
            fixture,
            runtime="langgraph",
            state=blocked.result.state.value,
            policy_decision=blocked.result.policy_decision,
            executions=len(executed),
        )
    return outcome(
        fixture,
        runtime="langgraph",
        state="CURRENT",
        policy_decision="allow",
        executions=len(executed),
    )


def run_openai_agents(fixture: ConformanceFixture) -> ConformanceOutcome:
    executed: list[str] = []
    freshness = openai_agents_tool_guardrail(
        depends_on=fixture.dependencies,
        store=fixture.store,
        audit_path=fixture.audit_path,
    )

    @function_tool(tool_input_guardrails=[freshness])
    def write_record(value: str) -> str:
        """Write one conformance record."""
        executed.append(value)
        return value

    model = ScriptedModel(
        [
            [
                function_call(
                    "write_record",
                    {"value": SENSITIVE_ARGUMENT},
                    call_id="openai-conformance-call",
                )
            ],
            [assistant_message("complete")],
        ]
    )
    try:
        asyncio.run(
            Runner.run(
                OpenAIAgent(name="conformance", model=model, tools=[write_record]),
                "write",
            )
        )
    except ToolInputGuardrailTripwireTriggered as blocked:
        result = blocked.output.output_info["freshctx"]
        return outcome(
            fixture,
            runtime="openai_agents",
            state=result["state"],
            policy_decision=result["policy_decision"],
            executions=len(executed),
        )
    return outcome(
        fixture,
        runtime="openai_agents",
        state="CURRENT",
        policy_decision="allow",
        executions=len(executed),
    )


async def _run_google_agent(tool_function: Callable[..., Any], callback: Any) -> list[Any]:
    agent = GoogleAgent(
        name="conformance",
        model=ScriptedGoogleToolModel(model="scripted"),
        tools=[tool_function],
        before_tool_callback=callback,
    )
    return await InMemoryRunner(agent=agent).run_debug("write", quiet=True)


def run_google_adk(fixture: ConformanceFixture) -> ConformanceOutcome:
    executed: list[str] = []

    def write_record(value: str) -> dict[str, str]:
        """Write one conformance record."""
        executed.append(value)
        return {"status": "written"}

    callback = google_adk_tool_callback(
        depends_on=fixture.dependencies,
        store=fixture.store,
        audit_path=fixture.audit_path,
    )
    events = asyncio.run(_run_google_agent(write_record, callback))
    response = next(
        part.function_response.response
        for event in events
        if event.content
        for part in event.content.parts
        if part.function_response
    )
    if response.get("status") == "blocked":
        result = response["freshctx"]
        return outcome(
            fixture,
            runtime="google_adk",
            state=result["state"],
            policy_decision=result["policy_decision"],
            executions=len(executed),
        )
    return outcome(
        fixture,
        runtime="google_adk",
        state="CURRENT",
        policy_decision="allow",
        executions=len(executed),
    )


def run_elevenlabs(fixture: ConformanceFixture) -> ConformanceOutcome:
    executed: list[str] = []
    client_tools = ClientTools()

    def write_record(parameters: dict[str, Any]) -> dict[str, str]:
        executed.append(parameters["value"])
        return {"status": "written"}

    register_elevenlabs_client_tool(
        client_tools,
        "write_record",
        write_record,
        depends_on=fixture.dependencies,
        store=fixture.store,
        audit_path=fixture.audit_path,
    )
    result = asyncio.run(
        client_tools.handle("write_record", {"value": SENSITIVE_ARGUMENT})
    )
    if result.get("status") == "blocked":
        blocked = result["freshctx"]
        return outcome(
            fixture,
            runtime="elevenlabs",
            state=blocked["state"],
            policy_decision=blocked["policy_decision"],
            executions=len(executed),
        )
    return outcome(
        fixture,
        runtime="elevenlabs",
        state="CURRENT",
        policy_decision="allow",
        executions=len(executed),
    )


async def _run_mcp(fixture: ConformanceFixture) -> ConformanceOutcome:
    executed: list[str] = []
    extension = FreshCtxMCPGuard(
        depends_on={"write_record": fixture.dependencies},
        store=fixture.store,
        protected_tools=["write_record"],
        audit_path=fixture.audit_path,
    )
    server = MCPServer("freshctx-conformance", extensions=[extension])

    @server.tool()
    def write_record(value: str) -> dict[str, str]:
        """Write one conformance record."""
        executed.append(value)
        return {"status": "written"}

    async with Client(server) as client:
        result = await client.call_tool(
            "write_record", {"value": SENSITIVE_ARGUMENT}
        )
    if result.is_error:
        return outcome(
            fixture,
            runtime="mcp",
            state=result.structured_content["state"],
            policy_decision=result.meta["com.freshctx/result"]["policy_decision"],
            executions=len(executed),
        )
    return outcome(
        fixture,
        runtime="mcp",
        state="CURRENT",
        policy_decision="allow",
        executions=len(executed),
    )


def run_mcp(fixture: ConformanceFixture) -> ConformanceOutcome:
    return asyncio.run(_run_mcp(fixture))


DRIVERS = {
    "agno": run_agno,
    "langgraph": run_langgraph,
    "openai_agents": run_openai_agents,
    "google_adk": run_google_adk,
    "elevenlabs": run_elevenlabs,
}
if "mcp" in RUNTIMES:
    DRIVERS["mcp"] = run_mcp


class FrameworkConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        unknown = set(RUNTIMES) - set(FRAMEWORK_RUNTIMES) - {"mcp"}
        if unknown:
            raise AssertionError(f"unknown conformance runtimes: {sorted(unknown)}")

    def test_equivalent_pre_action_matrix(self):
        observed: dict[tuple[str, str], ConformanceOutcome] = {}
        for runtime in RUNTIMES:
            for situation in SITUATIONS:
                with self.subTest(runtime=runtime, situation=situation):
                    fixture = ConformanceFixture(situation)
                    try:
                        result = DRIVERS[runtime](fixture)
                        observed[(runtime, situation)] = result
                        expected_allowed = situation in {"current", "unrelated_changed"}
                        self.assertEqual(result.status, "allowed" if expected_allowed else "blocked")
                        self.assertEqual(result.executions, 1 if expected_allowed else 0)
                        self.assertEqual(result.policy_decision, "allow" if expected_allowed else "block")
                        self.assertEqual(
                            result.state,
                            {
                                "current": "CURRENT",
                                "stale": "STALE_REASONING",
                                "unverifiable": "UNVERIFIABLE",
                                "unrelated_changed": "CURRENT",
                            }[situation],
                        )
                        self.assertFalse(result.secret_exposed)

                        metadata = fixture.integration_metadata(runtime)
                        self.assertEqual(metadata["contract"], CONTRACT_VERSION)
                        self.assertEqual(metadata["runtime"], runtime)
                        self.assertEqual(metadata["action"], "write_record")

                        events = read_audit_events(fixture.audit_path)
                        event_names = {event["event_type"] for event in events}
                        self.assertIn("policy_applied", event_names)
                        applied = [
                            event for event in events
                            if event["event_type"] == "policy_applied"
                        ][-1]
                        self.assertEqual(applied["details"]["state"], result.state)
                        self.assertEqual(
                            applied["details"]["policy_decision"],
                            result.policy_decision,
                        )
                        correlations = [
                            event for event in events
                            if event["event_type"] == "action_evidence_correlated"
                        ]
                        self.assertEqual(len(correlations), 1)
                        correlation = correlations[0]["details"]
                        self.assertEqual(
                            correlation["schema_version"],
                            "freshctx.action_evidence_correlation.v1",
                        )
                        self.assertEqual(correlation["runtime"], runtime)
                        self.assertEqual(correlation["action"], "write_record")
                        self.assertEqual(correlation["freshness_state"], result.state)
                        self.assertEqual(
                            correlation["policy_decision"], result.policy_decision
                        )
                        self.assertEqual(
                            correlation["boundary_outcome"],
                            "allowed" if expected_allowed else "blocked",
                        )
                        self.assertNotIn(SENSITIVE_ARGUMENT, repr(correlation))
                        if situation == "unverifiable":
                            self.assertEqual(correlation["observation_ids"], [])
                            self.assertEqual(
                                correlation["unresolved_dependency_ids"],
                                ["missing-conformance-dependency"],
                            )
                        else:
                            self.assertEqual(len(correlation["observation_ids"]), 1)
                            self.assertEqual(
                                correlation["unresolved_dependency_ids"], []
                            )
                        if expected_allowed:
                            self.assertIn("action_allowed", event_names)
                    finally:
                        fixture.close()

        self.assertEqual(len(observed), len(RUNTIMES) * len(SITUATIONS))
        for situation in SITUATIONS:
            normalized = {
                (
                    observed[(runtime, situation)].status,
                    observed[(runtime, situation)].state,
                    observed[(runtime, situation)].policy_decision,
                    observed[(runtime, situation)].executions,
                )
                for runtime in RUNTIMES
            }
            self.assertEqual(len(normalized), 1)

    @unittest.skipUnless("agno" in RUNTIMES, "Agno is not in this conformance environment")
    def test_agno_async_boundary_blocks_before_execution(self):
        fixture = ConformanceFixture("stale")
        executed: list[str] = []
        try:
            hook = agno_async_tool_hook(
                depends_on=fixture.dependencies,
                store=fixture.store,
                audit_path=fixture.audit_path,
            )

            @tool(tool_hooks=[hook])
            async def write_record(value: str) -> str:
                executed.append(value)
                return value

            async def run() -> None:
                with self.assertRaises(FreshCtxAgnoBlocked):
                    await FunctionCall(
                        function=write_record,
                        arguments={"value": SENSITIVE_ARGUMENT},
                    ).aexecute()

            asyncio.run(run())
            self.assertEqual(executed, [])
            self.assertFalse(fixture.secret_exposed())
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
