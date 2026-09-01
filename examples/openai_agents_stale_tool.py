"""A real SDK function tool blocked after its declared source changes.

No model or API key is required.
"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from agents import Agent, Runner, function_tool
from agents.exceptions import ToolInputGuardrailTripwireTriggered
from agents.testing import ScriptedModel, assistant_message, function_call

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.openai_agents import openai_agents_tool_guardrail


def run_demo(*, change_source: bool = True) -> dict[str, object]:
    """Run a bounded SDK tool call and return its observable outcome."""

    with TemporaryDirectory() as directory:
        root = Path(directory)
        config_path = root / "deployment.env"
        audit_path = root / "openai-agents-audit.jsonl"
        config_path.write_text("TARGET=staging\n", encoding="utf-8")
        store = MemoryStore()

        with guard(store=store, audit_path=audit_path):
            config = observe(config_path)
            with reasoning("select_deployment_target", depends_on=[config]) as decision:
                target = "staging"

        executed: list[str] = []
        freshness = openai_agents_tool_guardrail(
            depends_on=[decision], store=store, audit_path=audit_path
        )

        @function_tool(tool_input_guardrails=[freshness])
        async def deploy(target: str) -> str:
            """Deploy to the selected target."""
            executed.append(target)
            return f"deployed:{target}"

        if change_source:
            config_path.write_text("TARGET=production\n", encoding="utf-8")

        model = ScriptedModel(
            [
                [function_call("deploy", {"target": target}, call_id="openai-agents-demo-call")],
                [assistant_message("complete")],
            ]
        )
        agent = Agent(name="freshctx-demo", model=model, tools=[deploy])
        try:
            result = asyncio.run(Runner.run(agent, "deploy"))
        except ToolInputGuardrailTripwireTriggered as blocked:
            return {
                "sdk_status": "blocked",
                "executed": executed,
                "freshctx_state": blocked.output.output_info["freshctx"]["state"],
                "result": None,
            }
        return {
            "sdk_status": "success",
            "executed": executed,
            "freshctx_state": "CURRENT",
            "result": result.final_output,
        }


if __name__ == "__main__":
    outcome = run_demo()
    print(outcome)
    if outcome["sdk_status"] != "blocked" or outcome["executed"]:
        raise SystemExit("Expected FreshCtx to block the stale OpenAI Agents SDK tool call")
