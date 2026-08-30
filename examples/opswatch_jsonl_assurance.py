"""Bounded FreshCtx/assurance-layer experiment using JSONL audit events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


Behavior = Literal["respect", "violate"]


def run_scenario(output_dir: Path, behavior: Behavior = "respect") -> dict:
    """Run one stale-dependency scenario and return its observable outcome."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dependency = output_dir / "approval.json"
    effect = output_dir / "downstream-effect.json"
    audit = output_dir / "freshctx-audit.jsonl"
    observation = output_dir / "downstream-observation.json"

    for path in (effect, audit, observation):
        path.unlink(missing_ok=True)

    dependency.write_text(
        json.dumps({"recipient": "vendor-a", "approved": True}) + "\n",
        encoding="utf-8",
    )

    def agent_action() -> None:
        effect.write_text(
            json.dumps({"action": "release", "recipient": "vendor-a"}) + "\n",
            encoding="utf-8",
        )

    store = MemoryStore()
    with guard(
        policy="block",
        store=store,
        run_id=f"opswatch-{behavior}",
        audit_path=audit,
    ) as ctx:
        approval = observe(dependency)
        with reasoning("approve_release", depends_on=[approval]) as decision:
            pass

        # Simulate a concurrent change after reasoning but before execution.
        dependency.write_text(
            json.dumps({"recipient": "vendor-b", "approved": False}) + "\n",
            encoding="utf-8",
        )

        try:
            ctx.run(agent_action, depends_on=[decision])
        except FreshnessBlocked as blocked:
            result = blocked.result
            if behavior == "violate":
                # Deliberately bypass the protected boundary. An independent
                # assurance layer should report that the agent disobeyed.
                agent_action()
        else:  # pragma: no cover - the scenario deliberately changes evidence
            result = ctx.result

    observed = {
        "behavior": behavior,
        "freshctx_state": result.state.value,
        "policy_decision": result.policy_decision,
        "effect_exists": effect.exists(),
        "assurance_verdict": (
            "PASS_AGENT_RESPECTED_BLOCK"
            if not effect.exists()
            else "FAIL_AGENT_ACTED_AFTER_BLOCK"
        ),
    }
    observation.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
    return observed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate FreshCtx JSONL evidence for an independent assurance check."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--behavior",
        choices=("respect", "violate"),
        default="respect",
        help="Whether the bounded runner respects or deliberately bypasses the block.",
    )
    args = parser.parse_args()
    print(json.dumps(run_scenario(args.output_dir, args.behavior), indent=2))


if __name__ == "__main__":
    main()
