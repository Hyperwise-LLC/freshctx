"""FreshCtx receiving-side guard for the official A2A Python SDK."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from ..core import FreshnessBlocked
from ..errors import ConfigurationError
from ..model import utcnow
from .pre_action import PreActionBoundary, PreActionCall, blocked_contract_payload

try:
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.events import EventQueue
    from a2a.server.tasks.task_updater import TaskUpdater
    from a2a.types.a2a_pb2 import TaskState
except ImportError as exc:  # pragma: no cover - exercised without the optional extra
    raise ImportError(
        "FreshCtx A2A support requires: python -m pip install 'freshctx[a2a]'"
    ) from exc


A2A_EXTENSION_URI = "https://freshctx.com/extensions/a2a-delegation/v1"
A2A_DELEGATION_SCHEMA_VERSION = "freshctx.a2a_delegation.v1"
A2A_ATTESTATION_SCHEMA_VERSION = "freshctx.a2a_delegation_attestation.v1"


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("A2A delegation timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ConfigurationError("A2A delegation timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _label(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"A2A delegation {name} must not be empty")
    return value.strip()


@dataclass(frozen=True)
class A2ADelegation:
    """Privacy-bounded provenance passed between A2A agents."""

    root_correlation_id: str
    delegation_id: str
    origin_agent: str
    receiving_agent: str
    skill_id: str
    observation_ids: tuple[str, ...]
    created_at: str
    expires_at: str
    parent_delegation_id: str | None = None
    evidence_attestation_id: str | None = None
    task_id: str | None = None
    context_id: str | None = None
    schema_version: str = A2A_DELEGATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("root_correlation_id", "delegation_id", "origin_agent", "receiving_agent", "skill_id"):
            _label(name, getattr(self, name))
        if self.schema_version != A2A_DELEGATION_SCHEMA_VERSION:
            raise ConfigurationError("unsupported A2A delegation schema")
        if not self.observation_ids or any(not isinstance(item, str) or not item.strip() for item in self.observation_ids):
            raise ConfigurationError("A2A delegation requires observation IDs")
        if _parse_time(self.expires_at) <= _parse_time(self.created_at):
            raise ConfigurationError("A2A delegation expiry must follow creation")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["observation_ids"] = list(self.observation_ids)
        return value

    @classmethod
    def create(cls, *, root_correlation_id: str, origin_agent: str, receiving_agent: str,
               skill_id: str, observation_ids: Iterable[str], ttl_seconds: float,
               parent_delegation_id: str | None = None, evidence_attestation_id: str | None = None,
               task_id: str | None = None, context_id: str | None = None, now: str | None = None) -> "A2ADelegation":
        if not isinstance(ttl_seconds, (int, float)) or ttl_seconds <= 0:
            raise ConfigurationError("A2A delegation ttl_seconds must be positive")
        created = _parse_time(now or utcnow())
        return cls(root_correlation_id=root_correlation_id, delegation_id=str(uuid4()),
                   origin_agent=origin_agent, receiving_agent=receiving_agent, skill_id=skill_id,
                   observation_ids=tuple(observation_ids), created_at=created.isoformat(),
                   expires_at=(created + timedelta(seconds=float(ttl_seconds))).isoformat(),
                   parent_delegation_id=parent_delegation_id,
                   evidence_attestation_id=evidence_attestation_id, task_id=task_id, context_id=context_id)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A2ADelegation":
        data = dict(value)
        data["observation_ids"] = tuple(data.get("observation_ids", ()))
        try:
            return cls(**data)
        except TypeError as exc:
            raise ConfigurationError("invalid A2A delegation fields") from exc


@dataclass(frozen=True)
class A2ADelegationAttestation:
    delegation_id: str
    issuer: str
    key_id: str
    payload_digest: str
    signature: str
    issued_at: str
    algorithm: str = "hmac-sha256"
    schema_version: str = A2A_ATTESTATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A2ADelegationAttestation":
        try:
            return cls(**dict(value))
        except TypeError as exc:
            raise ConfigurationError("invalid A2A attestation fields") from exc


def _payload(delegation: A2ADelegation) -> bytes:
    return json.dumps(delegation.to_dict(), sort_keys=True, separators=(",", ":")).encode()


def attest_a2a_delegation(delegation: A2ADelegation, *, issuer: str, key_id: str,
                           key: bytes, now: str | None = None) -> A2ADelegationAttestation:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ConfigurationError("A2A attestation key must contain at least 32 bytes")
    payload = _payload(delegation)
    return A2ADelegationAttestation(
        delegation_id=delegation.delegation_id, issuer=_label("issuer", issuer), key_id=_label("key_id", key_id),
        payload_digest=hashlib.sha256(payload).hexdigest(),
        signature=hmac.new(key, payload, hashlib.sha256).hexdigest(), issued_at=_parse_time(now or utcnow()).isoformat())


def verify_a2a_delegation(delegation: A2ADelegation, attestation: A2ADelegationAttestation,
                          *, key: bytes, receiving_agent: str, now: str | None = None) -> tuple[bool, str]:
    if attestation.schema_version != A2A_ATTESTATION_SCHEMA_VERSION or attestation.algorithm != "hmac-sha256":
        return False, "unsupported_attestation"
    if delegation.receiving_agent != receiving_agent:
        return False, "wrong_recipient"
    current = _parse_time(now or utcnow())
    if current > _parse_time(delegation.expires_at):
        return False, "expired"
    if current < _parse_time(delegation.created_at) or current < _parse_time(attestation.issued_at):
        return False, "not_yet_valid"
    if attestation.delegation_id != delegation.delegation_id:
        return False, "delegation_mismatch"
    payload = _payload(delegation)
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(digest, attestation.payload_digest):
        return False, "payload_mismatch"
    if not hmac.compare_digest(hmac.new(key, payload, hashlib.sha256).hexdigest(), attestation.signature):
        return False, "signature_mismatch"
    return True, "verified"


def a2a_delegation_metadata(delegation: A2ADelegation, attestation: A2ADelegationAttestation) -> dict[str, Any]:
    return {A2A_EXTENSION_URI: {"delegation": delegation.to_dict(), "attestation": attestation.to_dict()}}


class FreshCtxA2AExecutor(AgentExecutor):
    """Guard an official A2A executor before delegated work begins."""

    def __init__(self, executor: AgentExecutor, *, receiving_agent: str, depends_on: Iterable[Any] | Callable[[RequestContext], Iterable[Any]],
                 store: Any, key_resolver: Callable[[str, str], bytes | None], audit_path: str = ".freshctx/a2a-audit.jsonl") -> None:
        self.executor = executor
        self.receiving_agent = _label("receiving_agent", receiving_agent)
        self.depends_on = depends_on
        self.store = store
        self.key_resolver = key_resolver
        self.audit_path = audit_path
        self.last_delegation: A2ADelegation | None = None
        self.last_correlation = None

    async def _reject(self, context: RequestContext, event_queue: EventQueue, reason: str, details: dict[str, Any] | None = None) -> None:
        task_id = context.task_id or "freshctx-a2a-rejected"
        context_id = context.context_id or "freshctx-a2a"
        metadata = {A2A_EXTENSION_URI: {"status": "blocked", "reason": reason, **(details or {})}}
        await TaskUpdater(event_queue, task_id, context_id).update_status(TaskState.TASK_STATE_REJECTED, metadata=metadata)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            envelope = context.metadata[A2A_EXTENSION_URI]
            delegation = A2ADelegation.from_dict(envelope["delegation"])
            attestation = A2ADelegationAttestation.from_dict(envelope["attestation"])
            key = self.key_resolver(attestation.issuer, attestation.key_id)
            if key is None:
                await self._reject(context, event_queue, "unknown_attestation_key")
                return
            valid, reason = verify_a2a_delegation(delegation, attestation, key=key, receiving_agent=self.receiving_agent)
        except (KeyError, TypeError, ConfigurationError):
            await self._reject(context, event_queue, "invalid_or_missing_delegation")
            return
        if not valid:
            await self._reject(context, event_queue, reason)
            return
        self.last_delegation = delegation
        dependencies = self.depends_on(context) if callable(self.depends_on) else self.depends_on
        boundary = PreActionBoundary(depends_on=dependencies, store=self.store, audit_path=self.audit_path)
        try:
            await boundary.invoke_async(
                PreActionCall(runtime="a2a", action=delegation.skill_id, execution_id=context.task_id or delegation.delegation_id),
                self.executor.execute, context, event_queue)
        except FreshnessBlocked as blocked:
            self.last_correlation = blocked.correlation
            await self._reject(context, event_queue, "freshctx_blocked", blocked_contract_payload(blocked))
            return
        self.last_correlation = boundary.last_correlation

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await self.executor.cancel(context, event_queue)
