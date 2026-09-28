from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FreshnessStatus(str, Enum):
    CURRENT = "CURRENT"
    STALE_SOURCE = "STALE_SOURCE"
    STALE_REASONING = "STALE_REASONING"
    UNVERIFIABLE = "UNVERIFIABLE"


# Backward-compatible v0.1 alias retained for early adopters.
FreshnessState = FreshnessStatus


class PolicyResponse(str, Enum):
    """Application-owned response to a freshness result.

    These values deliberately remain separate from ``FreshnessStatus``: evidence
    can be stale regardless of whether an application blocks, replans, or asks
    for renewed approval.
    """

    ALLOW = "allow"
    WARN = "warn"
    REFRESH = "refresh"
    BLOCK = "block"
    REPLAN = "replan"
    REQUIRE_APPROVAL = "require_approval"


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
    retryable: bool = False


@dataclass(frozen=True)
class RetryPolicy:
    """Opt-in bounds for evidence verification only, including the first attempt."""

    max_attempts: int = 1
    max_elapsed_ms: float | None = None
    backoff_ms: float = 0


@dataclass(frozen=True)
class ProtectedParameter:
    """Caller-declared lineage and digest of the value passed to an action."""

    dependencies: tuple[str, ...]
    value_digest: str


@dataclass(frozen=True)
class ActionAttempt:
    """Caller-supplied identity; FreshCtx does not infer intent or enforce counts."""

    operation_id: str | None = None
    attempt_id: str | None = None
    parent_attempt_id: str | None = None
    previous_outcome: str | None = None


@dataclass(frozen=True)
class CheckResult:
    state: FreshnessStatus
    subject_id: str
    causes: tuple[str, ...] = ()
    adapter_results: tuple[dict[str, Any], ...] = ()
    policy_decision: str = "allow"
    checked_at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        value["causes"] = list(self.causes)
        value["adapter_results"] = list(self.adapter_results)
        return value


@dataclass(frozen=True)
class ActionEvidenceCorrelation:
    """Portable link between one protected action and its checked evidence.

    The record contains identifiers and freshness outcomes only. It deliberately
    excludes action arguments, source contents, credentials, and any claim that
    the selected evidence was correct or authoritative.
    """

    correlation_id: str
    run_id: str
    action: str
    boundary: str
    subject_id: str
    declared_dependency_ids: tuple[str, ...]
    reasoning_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    unresolved_dependency_ids: tuple[str, ...]
    freshness_state: FreshnessStatus
    policy_decision: str
    boundary_outcome: str
    runtime: str | None = None
    execution_id: str | None = None
    operation_id: str | None = None
    attempt_id: str | None = None
    parent_attempt_id: str | None = None
    previous_outcome: str | None = None
    operation_identity_supplied: bool = False
    protected_parameter_ids: dict[str, str] = field(default_factory=dict)
    attempt_metadata_supplied: bool = False
    checked_at: str = field(default_factory=utcnow)
    created_at: str = field(default_factory=utcnow)
    schema_version: str = "freshctx.action_evidence_correlation.v1"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("attempt_metadata_supplied")
        if not self.attempt_metadata_supplied and not self.protected_parameter_ids:
            for key in ("operation_id", "attempt_id", "parent_attempt_id", "previous_outcome", "operation_identity_supplied", "protected_parameter_ids"):
                value.pop(key)
        value["freshness_state"] = self.freshness_state.value
        value["declared_dependency_ids"] = list(self.declared_dependency_ids)
        value["reasoning_ids"] = list(self.reasoning_ids)
        value["observation_ids"] = list(self.observation_ids)
        value["unresolved_dependency_ids"] = list(self.unresolved_dependency_ids)
        return value


@dataclass(frozen=True)
class ValidationReport:
    """Portable record for a bounded external FreshCtx validation."""

    scenario: str
    freshctx_version: str
    installation: str
    environment: dict[str, Any]
    expected: str
    observed: str
    verdict: str
    limitations: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    validator: str | None = None
    created_at: str = field(default_factory=utcnow)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["limitations"] = list(self.limitations)
        value["evidence"] = list(self.evidence)
        return value
