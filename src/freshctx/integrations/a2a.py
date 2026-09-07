"""FreshCtx receiving-side guard for the official A2A Python SDK."""

from __future__ import annotations

import hashlib
import hmac
import asyncio
import json
import sqlite3
import threading
import time
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


def a2a_action_intent_digest(value: bytes | str | Mapping[str, Any]) -> str:
    """Return a domain-separated digest without retaining the supplied intent.

    Applications decide which non-secret action fields are material. Raw tool
    arguments are consumed only while calculating this digest and are never
    copied into delegation metadata or FreshCtx audit records.
    """

    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    elif isinstance(value, Mapping):
        try:
            payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("A2A action intent must be canonically serializable") from exc
    else:
        raise ConfigurationError("A2A action intent must be bytes, text, or a mapping")
    return hashlib.sha256(b"freshctx.a2a_action_intent.v1\0" + payload).hexdigest()


class MemoryDelegationReplayStore:
    """Process-local atomic single-use store for delegation identifiers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consumed: dict[str, float] = {}

    def consume(self, delegation_id: str, expires_at: str) -> bool:
        expiry = _parse_time(expires_at).timestamp()
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            self._consumed = {key: value for key, value in self._consumed.items() if value >= now}
            if delegation_id in self._consumed:
                return False
            self._consumed[delegation_id] = expiry
            return True


class SQLiteDelegationReplayStore:
    """Cross-process atomic single-use store backed by SQLite."""

    def __init__(self, path: str) -> None:
        self.path = path
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS freshctx_a2a_consumed "
                "(delegation_id TEXT PRIMARY KEY, expires_at REAL NOT NULL)"
            )

    def consume(self, delegation_id: str, expires_at: str) -> bool:
        expiry = _parse_time(expires_at).timestamp()
        now = datetime.now(timezone.utc).timestamp()
        with sqlite3.connect(self.path, timeout=5) as connection:
            connection.execute("DELETE FROM freshctx_a2a_consumed WHERE expires_at < ?", (now,))
            try:
                connection.execute(
                    "INSERT INTO freshctx_a2a_consumed (delegation_id, expires_at) VALUES (?, ?)",
                    (delegation_id, expiry),
                )
            except sqlite3.IntegrityError:
                return False
        return True


class ValidationCircuitBreaker:
    """Small fail-closed breaker for repeated unverifiable validations."""

    def __init__(self, *, failure_threshold: int = 3, open_seconds: float = 30) -> None:
        if failure_threshold < 1 or open_seconds <= 0:
            raise ConfigurationError("A2A circuit breaker requires a positive threshold and open period")
        self.failure_threshold = int(failure_threshold)
        self.open_seconds = float(open_seconds)
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until = 0.0

    def allow_validation(self) -> bool:
        with self._lock:
            return time.monotonic() >= self._open_until

    def record_current(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = 0.0

    def record_unverifiable(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open_until = time.monotonic() + self.open_seconds


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
    action_intent_digest: str | None = None
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
        if self.action_intent_digest is not None and (
            len(self.action_intent_digest) != 64
            or any(character not in "0123456789abcdef" for character in self.action_intent_digest)
        ):
            raise ConfigurationError("A2A action intent digest must be a lowercase SHA-256 digest")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["observation_ids"] = list(self.observation_ids)
        if self.action_intent_digest is None:
            value.pop("action_intent_digest")
        return value

    @classmethod
    def create(cls, *, root_correlation_id: str, origin_agent: str, receiving_agent: str,
               skill_id: str, observation_ids: Iterable[str], ttl_seconds: float,
               parent_delegation_id: str | None = None, evidence_attestation_id: str | None = None,
               task_id: str | None = None, context_id: str | None = None,
               action_intent: bytes | str | Mapping[str, Any] | None = None,
               action_intent_digest: str | None = None, now: str | None = None) -> "A2ADelegation":
        if not isinstance(ttl_seconds, (int, float)) or ttl_seconds <= 0:
            raise ConfigurationError("A2A delegation ttl_seconds must be positive")
        created = _parse_time(now or utcnow())
        if action_intent is not None and action_intent_digest is not None:
            raise ConfigurationError("provide action_intent or action_intent_digest, not both")
        intent_digest = a2a_action_intent_digest(action_intent) if action_intent is not None else action_intent_digest
        return cls(root_correlation_id=root_correlation_id, delegation_id=str(uuid4()),
                   origin_agent=origin_agent, receiving_agent=receiving_agent, skill_id=skill_id,
                   observation_ids=tuple(observation_ids), created_at=created.isoformat(),
                   expires_at=(created + timedelta(seconds=float(ttl_seconds))).isoformat(),
                   parent_delegation_id=parent_delegation_id,
                   evidence_attestation_id=evidence_attestation_id, task_id=task_id, context_id=context_id,
                   action_intent_digest=intent_digest)

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
                 store: Any, key_resolver: Callable[[str, str], bytes | None], audit_path: str = ".freshctx/a2a-audit.jsonl",
                 action_intent: Callable[[RequestContext], bytes | str | Mapping[str, Any]] | None = None,
                 replay_store: Any | None = None, validation_attempts: int = 1,
                 validation_retry_delay_ms: float = 0, validation_retry_budget_ms: float | None = None,
                 circuit_breaker: ValidationCircuitBreaker | None = None) -> None:
        self.executor = executor
        self.receiving_agent = _label("receiving_agent", receiving_agent)
        self.depends_on = depends_on
        self.store = store
        self.key_resolver = key_resolver
        self.audit_path = audit_path
        if validation_attempts < 1:
            raise ConfigurationError("A2A validation_attempts must be at least 1")
        if validation_retry_delay_ms < 0:
            raise ConfigurationError("A2A validation_retry_delay_ms must not be negative")
        if validation_retry_budget_ms is not None and validation_retry_budget_ms <= 0:
            raise ConfigurationError("A2A validation_retry_budget_ms must be positive")
        self.action_intent = action_intent
        self.replay_store = replay_store
        self.validation_attempts = int(validation_attempts)
        self.validation_retry_delay_ms = float(validation_retry_delay_ms)
        self.validation_retry_budget_ms = validation_retry_budget_ms
        self.circuit_breaker = circuit_breaker
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
        if self.action_intent is not None:
            try:
                expected_intent = a2a_action_intent_digest(self.action_intent(context))
            except Exception:
                await self._reject(context, event_queue, "action_intent_unverifiable")
                return
            if delegation.action_intent_digest is None:
                await self._reject(context, event_queue, "missing_action_intent")
                return
            if not hmac.compare_digest(expected_intent, delegation.action_intent_digest):
                await self._reject(context, event_queue, "action_intent_mismatch")
                return
        if self.circuit_breaker is not None and not self.circuit_breaker.allow_validation():
            await self._reject(context, event_queue, "validation_circuit_open")
            return
        if self.replay_store is not None:
            try:
                consumed = self.replay_store.consume(delegation.delegation_id, delegation.expires_at)
            except Exception:
                await self._reject(context, event_queue, "replay_store_unverifiable")
                return
            if not consumed:
                await self._reject(context, event_queue, "delegation_replayed")
                return
        self.last_delegation = delegation
        dependencies = self.depends_on(context) if callable(self.depends_on) else self.depends_on
        started = time.monotonic()
        for attempt in range(1, self.validation_attempts + 1):
            boundary = PreActionBoundary(depends_on=dependencies, store=self.store, audit_path=self.audit_path)
            try:
                await boundary.invoke_async(
                    PreActionCall(runtime="a2a", action=delegation.skill_id, execution_id=context.task_id or delegation.delegation_id),
                    self.executor.execute, context, event_queue)
            except FreshnessBlocked as blocked:
                self.last_correlation = blocked.correlation
                elapsed_ms = (time.monotonic() - started) * 1000
                can_retry = (
                    blocked.result.state.value == "UNVERIFIABLE"
                    and attempt < self.validation_attempts
                    and (self.validation_retry_budget_ms is None or elapsed_ms < self.validation_retry_budget_ms)
                )
                if can_retry:
                    delay = self.validation_retry_delay_ms / 1000
                    if self.validation_retry_budget_ms is not None:
                        remaining = max(0, (self.validation_retry_budget_ms - elapsed_ms) / 1000)
                        delay = min(delay, remaining)
                    if delay:
                        await asyncio.sleep(delay)
                    continue
                details = blocked_contract_payload(blocked)
                details["validation_attempts"] = attempt
                if blocked.result.state.value == "UNVERIFIABLE" and self.circuit_breaker is not None:
                    self.circuit_breaker.record_unverifiable()
                await self._reject(context, event_queue, "freshctx_blocked", details)
                return
            self.last_correlation = boundary.last_correlation
            if self.circuit_breaker is not None:
                self.circuit_breaker.record_current()
            return

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await self.executor.cancel(context, event_queue)
