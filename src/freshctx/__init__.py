from importlib.metadata import PackageNotFoundError, version

from .adapters import register_adapter
from .core import FreshnessBlocked, guard, observe, reasoning
from .errors import AuditFailure, ConfigurationError, FilesystemLimitExceeded, FilesystemScopeError, FreshCtxError, StorageConflictError
from .model import CheckResult, FreshnessState, FreshnessStatus, ObservationToken, PolicyResponse, ReasoningNode
from .store import MemoryStore, SQLiteStore

try:
    __version__ = version("freshctx")
except PackageNotFoundError:
    # Supports running examples and adapter tests directly from a source checkout.
    __version__ = "0.2.0"

__all__ = ["AuditFailure", "CheckResult", "ConfigurationError", "FilesystemLimitExceeded", "FilesystemScopeError", "FreshCtxError", "FreshnessBlocked", "FreshnessState", "FreshnessStatus", "MemoryStore", "ObservationToken", "PolicyResponse", "ReasoningNode", "SQLiteStore", "StorageConflictError", "__version__", "guard", "observe", "reasoning", "register_adapter"]
