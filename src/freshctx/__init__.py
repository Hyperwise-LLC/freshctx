from importlib.metadata import PackageNotFoundError, version

from .adapters import register_adapter
from .conformance import adapter_contract_issues
from .core import FreshnessBlocked, guard, observe, reasoning
from .errors import AuditFailure, ConfigurationError, FilesystemLimitExceeded, FilesystemScopeError, FreshCtxError, StorageConflictError, StorageCorruptionError, StorageMigrationError
from .model import ActionEvidenceCorrelation, CheckResult, FreshnessState, FreshnessStatus, ObservationToken, PolicyResponse, ReasoningNode, ValidationReport
from .store import MemoryStore, SCHEMA_VERSION, SQLiteStore

try:
    __version__ = version("freshctx")
except PackageNotFoundError:
    # Supports running examples and adapter tests directly from a source checkout.
    __version__ = "0.10.0"

__all__ = ["ActionEvidenceCorrelation", "AuditFailure", "CheckResult", "ConfigurationError", "FilesystemLimitExceeded", "FilesystemScopeError", "FreshCtxError", "FreshnessBlocked", "FreshnessState", "FreshnessStatus", "MemoryStore", "ObservationToken", "PolicyResponse", "ReasoningNode", "SCHEMA_VERSION", "SQLiteStore", "StorageConflictError", "StorageCorruptionError", "StorageMigrationError", "ValidationReport", "__version__", "adapter_contract_issues", "guard", "observe", "reasoning", "register_adapter"]
