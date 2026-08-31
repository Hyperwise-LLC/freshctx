"""An actual Agno tool call blocked after its declared source changes.

No model or external API is required.  The example exercises Agno's real tool
execution and hook chain with a deliberately stale deployment decision.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from agno.tools import tool
from agno.tools.function import FunctionCall

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.agno import FreshCtxAgnoBlocked, agno_tool_hook


def run_demo(*, change_source: bool = True) -> dict[str, object]:
    """Run a bounded Agno tool call and return its observable outcome."""

    with TemporaryDirectory() as directory:
        root = Path(directory)
        config_path = root / "deployment.env"
        audit_path = root / "agno-audit.jsonl"
        config_path.write_text("TARGET=staging\n", encoding="utf-8")
        store = MemoryStore()

        with guard(store=store, audit_path=audit_path):
            config = observe(config_path)
            with reasoning("select_deployment_target", depends_on=[config]) as decision:
                target = "staging"

        executed: list[str] = []
        freshness_hook = agno_tool_hook(
            depends_on=[decision],
            store=store,
            audit_path=audit_path,
        )

        @tool(tool_hooks=[freshness_hook])
        def deploy(target: str) -> str:
            """Deploy to the selected target."""

            executed.append(target)
            return f"deployed:{target}"

        if change_source:
            config_path.write_text("TARGET=production\n", encoding="utf-8")

        try:
            result = FunctionCall(function=deploy, arguments={"target": target}).execute()
        except FreshCtxAgnoBlocked as blocked:
            return {
                "agno_status": "blocked",
                "executed": executed,
                "freshctx_state": blocked.result.state.value,
                "result": None,
            }
        return {
            "agno_status": result.status,
            "executed": executed,
            "freshctx_state": "CURRENT",
            "result": result.result,
        }


if __name__ == "__main__":
    outcome = run_demo()
    print(outcome)
    if outcome["agno_status"] != "blocked" or outcome["executed"]:
        raise SystemExit("Expected FreshCtx to block the stale Agno tool call")
