"""Shared fixtures and normalized results for framework conformance tests."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from freshctx import MemoryStore, guard, observe, reasoning


SENSITIVE_ARGUMENT = "customer-secret-9f6d"
CONTRACT_VERSION = "freshctx.pre_action.experimental.v1"


@dataclass(frozen=True)
class ConformanceOutcome:
    runtime: str
    situation: str
    status: str
    state: str
    policy_decision: str
    executions: int
    secret_exposed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ConformanceFixture:
    """Two-source fixture used unchanged by every framework driver."""

    def __init__(self, situation: str):
        self.situation = situation
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.required_source = self.root / "required-state.txt"
        self.unrelated_source = self.root / "unrelated-state.txt"
        self.audit_path = self.root / "audit.jsonl"
        self.required_source.write_text("version=1\n", encoding="utf-8")
        self.unrelated_source.write_text("version=1\n", encoding="utf-8")
        self.store = MemoryStore()

        with guard(store=self.store, audit_path=self.audit_path):
            required = observe(self.required_source)
            self.unrelated = observe(self.unrelated_source)
            with reasoning("choose_action", depends_on=[required]) as decision:
                pass
        self.dependencies: list[Any] = [decision]

        if situation == "stale":
            self.required_source.write_text("version=2\n", encoding="utf-8")
        elif situation == "unverifiable":
            self.dependencies = ["missing-conformance-dependency"]
        elif situation == "unrelated_changed":
            self.unrelated_source.write_text("version=2\n", encoding="utf-8")
        elif situation != "current":
            raise ValueError(f"unsupported conformance situation: {situation}")

    def close(self) -> None:
        self.temporary_directory.cleanup()

    def secret_exposed(self) -> bool:
        stored = repr(self.store.objects)
        audit = self.audit_path.read_text(encoding="utf-8")
        return SENSITIVE_ARGUMENT in stored or SENSITIVE_ARGUMENT in audit

    def integration_metadata(self, runtime: str) -> dict[str, str]:
        nodes = [
            value
            for value in self.store.objects.values()
            if getattr(value, "kind", None) == "pre_action_integration"
            and value.metadata.get("runtime") == runtime
        ]
        if len(nodes) != 1:
            raise AssertionError(
                f"expected one {runtime} pre-action integration node, found {len(nodes)}"
            )
        return nodes[0].metadata


def outcome(
    fixture: ConformanceFixture,
    *,
    runtime: str,
    state: str,
    policy_decision: str,
    executions: int,
) -> ConformanceOutcome:
    state = getattr(state, "value", state)
    policy_decision = getattr(policy_decision, "value", policy_decision)
    status = "allowed" if policy_decision == "allow" else "blocked"
    return ConformanceOutcome(
        runtime=runtime,
        situation=fixture.situation,
        status=status,
        state=state,
        policy_decision=policy_decision,
        executions=executions,
        secret_exposed=fixture.secret_exposed(),
    )


def read_audit_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
