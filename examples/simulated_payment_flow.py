"""Fully simulated payment freshness scenarios; no payment is authorized or sent."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


SCENARIOS = ("current", "balance_changed", "approval_changed", "unrelated_changed")


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def run_scenario(root: Path, scenario: str) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    root.mkdir(parents=True, exist_ok=True)
    state = root / "state"
    state.mkdir(exist_ok=True)
    audit = root / f"{scenario}-audit.jsonl"
    effect = root / f"{scenario}-simulated-effect.json"
    audit.unlink(missing_ok=True)
    effect.unlink(missing_ok=True)

    files = {
        "balance": state / "balance.json",
        "account": state / "account.json",
        "limit": state / "limit.json",
        "approval": state / "approval.json",
        "unrelated": state / "unrelated.json",
    }
    initial = {
        "balance": {"available": 2500, "currency": "USD"},
        "account": {"status": "open"},
        "limit": {"per_payment": 1000, "currency": "USD"},
        "approval": {"payment_id": "pay-sim-001", "approved": True},
        "unrelated": {"support_banner": "normal"},
    }
    for name, value in initial.items():
        _write(files[name], value)

    store = MemoryStore()
    executed = []
    result = None
    with guard(policy="block", store=store, run_id=f"payment-{scenario}", audit_path=audit) as ctx:
        tokens = {name: observe(path) for name, path in files.items()}
        with reasoning(
            "payment_readiness",
            depends_on=[tokens["balance"], tokens["account"], tokens["limit"], tokens["approval"]],
            metadata={"payment_id": "pay-sim-001", "amount": 500, "currency": "USD"},
        ) as decision:
            pass

        if scenario == "balance_changed":
            _write(files["balance"], {"available": 100, "currency": "USD"})
        elif scenario == "approval_changed":
            _write(files["approval"], {"payment_id": "pay-sim-001", "approved": False})
        elif scenario == "unrelated_changed":
            _write(files["unrelated"], {"support_banner": "maintenance"})

        try:
            ctx.run(
                lambda: (executed.append(True), _write(effect, {"simulated": True})),
                depends_on=[decision],
                boundary="simulated_payment_submission",
            )
        except FreshnessBlocked as blocked:
            result = blocked.result
        else:
            result = ctx.result

    assert result is not None
    return {
        "scenario": scenario,
        "state": result.state.value,
        "policy_decision": result.policy_decision,
        "causes": list(result.causes),
        "simulated_action_executed": bool(executed),
        "audit_path": str(audit),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scenario", choices=(*SCENARIOS, "all"), default="all")
    args = parser.parse_args()
    output = args.output_dir or Path(tempfile.mkdtemp(prefix="freshctx-payment-"))
    scenarios = SCENARIOS if args.scenario == "all" else (args.scenario,)
    print(json.dumps([run_scenario(output / name, name) for name in scenarios], indent=2))


if __name__ == "__main__":
    main()
