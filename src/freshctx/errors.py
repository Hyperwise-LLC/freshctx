"""Public FreshCtx exception hierarchy."""


class FreshCtxError(RuntimeError):
    """Base class for FreshCtx runtime errors."""


class AuditFailure(FreshCtxError):
    """Raised when a required audit event cannot be persisted."""


class ConfigurationError(FreshCtxError):
    """Raised for invalid FreshCtx configuration."""


class StorageConflictError(FreshCtxError):
    """Raised when an existing immutable ID is written with different content."""


class FilesystemLimitExceeded(FreshCtxError):
    """Raised when filesystem observation exceeds a configured work limit."""


class FilesystemScopeError(FreshCtxError):
    """Raised when filesystem observation would cross its configured root."""
