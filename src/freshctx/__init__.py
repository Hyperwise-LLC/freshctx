from importlib.metadata import PackageNotFoundError, version

from .adapters import register_adapter
from .core import AuditFailure, ConfigurationError, FreshCtxError, FreshnessBlocked, guard, observe, reasoning
from .model import CheckResult, DependencyEdge, FreshnessState, FreshnessStatus, ObservationToken, ReasoningNode
from .store import MemoryStore, SQLiteStore

try:
    __version__ = version("freshctx")
except PackageNotFoundError:
    # Supports running examples and adapter tests directly from a source checkout.
    __version__ = "0.1.0"

__all__ = ["AuditFailure", "CheckResult", "ConfigurationError", "DependencyEdge", "FreshCtxError", "FreshnessBlocked", "FreshnessState", "FreshnessStatus", "MemoryStore", "ObservationToken", "ReasoningNode", "SQLiteStore", "__version__", "guard", "observe", "reasoning", "register_adapter"]
