"""A real Google ADK tool call blocked after its declared source changes.

The example uses a deterministic local model, so it exercises ADK's installed
agent and tool pipeline without requiring a Gemini API key or network access.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.google_adk import google_adk_tool_callback


class _ScriptedToolModel(BaseLlm):
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
                                name="deploy_release",
                                args={"environment": "staging"},
                                id="google-adk-call-1",
                            )
                        )
                    ],
                )
            )
        else:
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="complete")]))


async def _run(change_source: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "deployment.txt"
        source.write_text("version=1\n", encoding="utf-8")
        audit = root / "audit.jsonl"
        store = MemoryStore()
        executed: list[str] = []

        with guard(store=store, audit_path=audit):
            token = observe(source)
            with reasoning("approve_deployment", depends_on=[token]) as decision:
                pass

        async def deploy_release(environment: str) -> dict[str, str]:
            """Deploy a release to one environment."""
            executed.append(environment)
            return {"status": "deployed", "environment": environment}

        freshness = google_adk_tool_callback(
            depends_on=[decision],
            store=store,
            tool_names=["deploy_release"],
            audit_path=audit,
        )
        agent = Agent(
            name="freshctx_google_adk_demo",
            model=_ScriptedToolModel(model="freshctx-scripted"),
            tools=[deploy_release],
            before_tool_callback=freshness,
        )
        if change_source:
            source.write_text("version=2\n", encoding="utf-8")

        events = await InMemoryRunner(agent=agent).run_debug("deploy", quiet=True)
        tool_response = next(
            part.function_response.response
            for event in events
            if event.content
            for part in event.content.parts
            if part.function_response
        )
        return {
            "adk_status": tool_response.get("status"),
            "freshctx_state": tool_response.get("freshctx", {}).get("state", "CURRENT"),
            "executed": executed,
        }


def run_demo(*, change_source: bool = True) -> dict[str, Any]:
    return asyncio.run(_run(change_source))


if __name__ == "__main__":
    blocked = run_demo()
    print(blocked)
    if blocked != {"adk_status": "blocked", "freshctx_state": "STALE_REASONING", "executed": []}:
        raise SystemExit("Expected FreshCtx to block the stale Google ADK tool call")
