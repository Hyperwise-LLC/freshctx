"""Minimal LangGraph action node protected by FreshCtx."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


class DeploymentState(TypedDict):
    target: str
    deployed: bool


def deploy(target: str) -> None:
    print(f"DEPLOYED to {target}")


def run_demo() -> bool:
    """Return True when FreshCtx blocks the deliberately stale action."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config_path = root / "deployment.env"
        config_path.write_text("TARGET=staging\n", encoding="utf-8")

        with guard(
            policy="block",
            store=MemoryStore(),
            audit_path=root / "audit.jsonl",
        ) as ctx:
            config = observe(config_path)
            with reasoning("choose_target", depends_on=[config]) as decision:
                target = "staging"

            def change_config(state: DeploymentState) -> dict:
                # Simulates another process changing state after planning.
                config_path.write_text("TARGET=production\n", encoding="utf-8")
                return {}

            def protected_deploy(state: DeploymentState) -> dict:
                ctx.run(deploy, state["target"], depends_on=[decision])
                return {"deployed": True}

            builder = StateGraph(DeploymentState)
            builder.add_node("concurrent_change", change_config)
            builder.add_node("deploy", protected_deploy)
            builder.add_edge(START, "concurrent_change")
            builder.add_edge("concurrent_change", "deploy")
            builder.add_edge("deploy", END)

            try:
                builder.compile().invoke({"target": target, "deployed": False})
            except FreshnessBlocked as exc:
                print(f"BLOCKED: {exc.result.state.value}")
                return True

    return False


if __name__ == "__main__":
    if not run_demo():
        raise SystemExit("Expected FreshCtx to block the stale LangGraph action")
