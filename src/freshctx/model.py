from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FreshnessState(str, Enum):
    CURRENT = "CURRENT"
    STALE_SOURCE = "STALE_SOURCE"
    STALE_REASONING = "STALE_REASONING"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class ObservationToken:
    adapter: str
    locator: str
    fingerprint: str
    validator: str = "v1"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    observed_at: str = field(default_factory=utcnow)


@dataclass(frozen=True)
class ReasoningNode:
    kind: str
    dependencies: tuple[str, ...]
    digest: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utcnow)


@dataclass(frozen=True)
class AdapterResult:
    outcome: str
    checked_at: str = field(default_factory=utcnow)
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


@dataclass(frozen=True)
class CheckResult:
    state: FreshnessState
    subject_id: str
    causes: tuple[str, ...] = ()
    adapter_results: tuple[dict[str, Any], ...] = ()
    policy_decision: str = "allow"
    checked_at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return value
