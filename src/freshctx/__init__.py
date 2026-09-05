from importlib.metadata import PackageNotFoundError, version

from .adapters import register_adapter
from .attestation import ATTESTATION_SCHEMA_VERSION, AttestationVerification, EvidenceAttestation, attest_correlation, verify_attestation
from .conformance import adapter_contract_issues
from .core import FreshnessBlocked, guard, observe, reasoning
from .errors import AuditFailure, ConfigurationError, FilesystemLimitExceeded, FilesystemScopeError, FreshCtxError, StorageConflictError, StorageCorruptionError, StorageMigrationError
from .model import ActionEvidenceCorrelation, CheckResult, FreshnessState, FreshnessStatus, ObservationToken, PolicyResponse, ReasoningNode, ValidationReport
from .provenance import AgentSourceSelection, ObservedEvidenceReceipt, ObservedReadCapture, PROVENANCE_ENFORCEMENT_SCHEMA_VERSION, PROVENANCE_SCHEMA_VERSION, ProvenanceAssessment, ProvenanceBlocked, ProvenanceBoundary, ProvenanceEnforcement, SourceDiscoveryAgent, SourceReadEvent
from .store import MemoryStore, SCHEMA_VERSION, SQLiteStore

try:
    __version__ = version("freshctx")
except PackageNotFoundError:
    # Supports running examples and adapter tests directly from a source checkout.
    __version__ = "0.13.0"

__all__ = ["ATTESTATION_SCHEMA_VERSION", "ActionEvidenceCorrelation", "AgentSourceSelection", "AttestationVerification", "AuditFailure", "CheckResult", "ConfigurationError", "EvidenceAttestation", "FilesystemLimitExceeded", "FilesystemScopeError", "FreshCtxError", "FreshnessBlocked", "FreshnessState", "FreshnessStatus", "MemoryStore", "ObservationToken", "ObservedEvidenceReceipt", "ObservedReadCapture", "PROVENANCE_ENFORCEMENT_SCHEMA_VERSION", "PROVENANCE_SCHEMA_VERSION", "PolicyResponse", "ProvenanceAssessment", "ProvenanceBlocked", "ProvenanceBoundary", "ProvenanceEnforcement", "ReasoningNode", "SCHEMA_VERSION", "SQLiteStore", "SourceDiscoveryAgent", "SourceReadEvent", "StorageConflictError", "StorageCorruptionError", "StorageMigrationError", "ValidationReport", "__version__", "adapter_contract_issues", "attest_correlation", "guard", "observe", "reasoning", "register_adapter", "verify_attestation"]
