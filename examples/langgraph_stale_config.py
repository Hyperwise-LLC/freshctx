"""Minimal LangGraph action node protected by FreshCtx."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning
from freshctx.integrations.langgraph import langgraph_action_node


class DeploymentState(TypedDict):
    target: str
    deployed: bool
    freshctx_decision: Any
    execution_id: str


def deploy(target: str) -> None:
    print(f"DEPLOYED to {target}")


def run_demo(*, change_source: bool = True) -> bool:
    """Return True when the graph produces the expected protected outcome."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config_path = root / "deployment.env"
        config_path.write_text("TARGET=staging\n", encoding="utf-8")
        store = MemoryStore()

        with guard(
            policy="block",
            store=store,
            audit_path=root / "audit.jsonl",
        ):
            config = observe(config_path)
            with reasoning("choose_target", depends_on=[config]) as decision:
                target = "staging"

        def change_config(state: DeploymentState) -> dict:
            if change_source:
                # Simulates another process changing state after planning.
                config_path.write_text("TARGET=production\n", encoding="utf-8")
            return {}

        def deploy_node(state: DeploymentState) -> dict:
            deploy(state["target"])
            return {"deployed": True}

        protected_deploy = langgraph_action_node(
            deploy_node,
            depends_on=lambda state: [state["freshctx_decision"]],
            store=store,
            action_name="deploy",
            execution_id=lambda state: state["execution_id"],
            audit_path=root / "audit.jsonl",
        )

        builder = StateGraph(DeploymentState)
        builder.add_node("concurrent_change", change_config)
        builder.add_node("deploy", protected_deploy)
        builder.add_edge(START, "concurrent_change")
        builder.add_edge("concurrent_change", "deploy")
        builder.add_edge("deploy", END)

        try:
            result = builder.compile().invoke(
                {
                    "target": target,
                    "deployed": False,
                    "freshctx_decision": decision,
                    "execution_id": "langgraph-example-run",
                }
            )
        except FreshnessBlocked as exc:
            print(f"BLOCKED: {exc.result.state.value}")
            return change_source

    return not change_source and result["deployed"]


if __name__ == "__main__":
    if not run_demo():
        raise SystemExit("Expected FreshCtx to block the stale LangGraph action")
