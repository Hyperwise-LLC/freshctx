from __future__ import annotations

from typing import Any

from .model import AdapterResult


VALID_OUTCOMES = frozenset({"equivalent", "changed", "indeterminate"})


def adapter_contract_issues(adapter: Any) -> tuple[str, ...]:
    """Return structural contract violations for a FreshCtx adapter."""
    issues = []
    if not isinstance(getattr(adapter, "name", None), str) or not adapter.name:
        issues.append("adapter.name must be a non-empty string")
    if not callable(getattr(adapter, "observe", None)):
        issues.append("adapter.observe must be callable")
    if not callable(getattr(adapter, "validate", None)):
        issues.append("adapter.validate must be callable")
    if not isinstance(getattr(adapter, "thread_safe", False), bool):
        issues.append("adapter.thread_safe must be a boolean")
    return tuple(issues)


def normalize_adapter_result(value: Any) -> AdapterResult:
    """Fail closed when an adapter violates the validation result contract."""
    if not isinstance(value, AdapterResult):
        return AdapterResult("indeterminate", error_code="invalid_adapter_result_type")
    if value.outcome not in VALID_OUTCOMES:
        return AdapterResult(
            "indeterminate",
            evidence=value.evidence,
            error_code="invalid_adapter_outcome",
        )
    return value
