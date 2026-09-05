"""Bounded, process-local signing for action/evidence correlation records."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .errors import ConfigurationError
from .model import ActionEvidenceCorrelation, utcnow


ATTESTATION_SCHEMA_VERSION = "freshctx.evidence_attestation.v1"


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("attestation timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ConfigurationError("attestation timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require_label(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"attestation {name} must not be empty")
    return value.strip()


def _require_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ConfigurationError("attestation key must contain at least 32 bytes")
    return key


def _payload(correlation: ActionEvidenceCorrelation) -> bytes:
    return json.dumps(
        correlation.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass(frozen=True)
class EvidenceAttestation:
    """Integrity receipt for one exact action/evidence correlation record."""

    attestation_id: str
    correlation_id: str
    issuer: str
    key_id: str
    payload_digest: str
    signature: str
    issued_at: str
    expires_at: str
    algorithm: str = "hmac-sha256"
    schema_version: str = ATTESTATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attestation_id": self.attestation_id,
            "correlation_id": self.correlation_id,
            "issuer": self.issuer,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "payload_digest": self.payload_digest,
            "signature": self.signature,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class AttestationVerification:
    """Independent attestation result; never a FreshCtx freshness state."""

    valid: bool
    reason: str


def attest_correlation(
    correlation: ActionEvidenceCorrelation,
    *,
    issuer: str,
    key_id: str,
    key: bytes,
    ttl_seconds: float,
    now: str | None = None,
) -> EvidenceAttestation:
    """Sign one correlation record with a bounded validity period."""

    issuer = _require_label("issuer", issuer)
    key_id = _require_label("key_id", key_id)
    key = _require_key(key)
    if not isinstance(ttl_seconds, (int, float)) or ttl_seconds <= 0:
        raise ConfigurationError("attestation ttl_seconds must be positive")
    issued_at = now or utcnow()
    issued = _timestamp(issued_at)
    expires_at = (issued + timedelta(seconds=float(ttl_seconds))).isoformat()
    payload = _payload(correlation)
    digest = hashlib.sha256(payload).hexdigest()
    signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return EvidenceAttestation(
        attestation_id=str(uuid4()),
        correlation_id=correlation.correlation_id,
        issuer=issuer,
        key_id=key_id,
        payload_digest=digest,
        signature=signature,
        issued_at=issued.isoformat(),
        expires_at=expires_at,
    )


def verify_attestation(
    attestation: EvidenceAttestation,
    correlation: ActionEvidenceCorrelation,
    *,
    key: bytes,
    now: str | None = None,
) -> AttestationVerification:
    """Verify scope, expiry, digest, and signature without changing freshness."""

    key = _require_key(key)
    if attestation.schema_version != ATTESTATION_SCHEMA_VERSION:
        return AttestationVerification(False, "unsupported_schema")
    if attestation.algorithm != "hmac-sha256":
        return AttestationVerification(False, "unsupported_algorithm")
    if attestation.correlation_id != correlation.correlation_id:
        return AttestationVerification(False, "correlation_mismatch")
    current = _timestamp(now or utcnow())
    if current < _timestamp(attestation.issued_at):
        return AttestationVerification(False, "not_yet_valid")
    if current > _timestamp(attestation.expires_at):
        return AttestationVerification(False, "expired")
    payload = _payload(correlation)
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(attestation.payload_digest, digest):
        return AttestationVerification(False, "payload_mismatch")
    expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(attestation.signature, expected):
        return AttestationVerification(False, "signature_mismatch")
    return AttestationVerification(True, "verified")
