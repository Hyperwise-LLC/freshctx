"""Experimental framework-neutral pre-action integration contract.

This module is intentionally not exported from :mod:`freshctx.integrations`.
Its API may change while FreshCtx tests the same contract against multiple
agent runtimes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from os import PathLike
from typing import Any

from ..core import FreshnessBlocked, guard, reasoning
from ..errors import ConfigurationError
from ..model import ActionAttempt, ProtectedParameter, RetryPolicy


EXPERIMENTAL_PRE_ACTION_CONTRACT = "freshctx.pre_action.experimental.v1"


def blocked_contract_payload(blocked: FreshnessBlocked) -> dict[str, Any]:
    """Return the portable, non-sensitive blocked result used by integrations."""

    return {
        "freshctx": blocked.result.to_dict(),
        "correlation": (
            blocked.correlation.to_dict() if blocked.correlation is not None else None
        ),
        "contract": EXPERIMENTAL_PRE_ACTION_CONTRACT,
    }


@dataclass(frozen=True)
class PreActionCall:
    """Non-sensitive identity for one framework action boundary.

    Arguments are deliberately absent. Framework bridges pass arguments only
    to the continuation so credentials and business payloads are not copied
    into FreshCtx reasoning metadata.
    """

    runtime: str
    action: str
    execution_id: str | None = None
    operation_id: str | None = None
    attempt_id: str | None = None
    parent_attempt_id: str | None = None
    previous_outcome: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, str) or not self.runtime.strip():
            raise ConfigurationError("pre-action runtime must not be empty")
        if not isinstance(self.action, str) or not self.action.strip():
            raise ConfigurationError("pre-action action must not be empty")
        if self.execution_id is not None and (
            not isinstance(self.execution_id, str) or not self.execution_id.strip()
        ):
            raise ConfigurationError("pre-action execution_id must not be empty")
        for field_name in ("operation_id", "attempt_id", "parent_attempt_id", "previous_outcome"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ConfigurationError(f"pre-action {field_name} must not be empty")

    @property
    def boundary(self) -> str:
        return f"{self.runtime}.action:{self.action}"


class PreActionBoundary:
    """Validate declared evidence immediately before invoking a continuation.

    A framework bridge owns argument mapping and framework-specific exception
    translation. This boundary owns only FreshCtx validation, policy handling,
    audit correlation, and the guarantee that a blocking result prevents the
    supplied continuation from starting.
    """

    def __init__(
        self,
        *,
        depends_on: Iterable[Any],
        store: Any,
        policy: str = "block",
        audit_path: str | PathLike[str] = ".freshctx/integration-audit.jsonl",
        validation_workers: int = 1,
        validation_budget_ms: float | None = None,
        retry_policy: RetryPolicy | None = None,
        protected_parameters: dict[str, ProtectedParameter] | None = None,
        parameter_values: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(depends_on, (str, bytes)):
            raise ConfigurationError("pre-action dependencies must be a non-empty iterable of FreshCtx objects or IDs")
        try:
            dependencies = tuple(depends_on)
        except TypeError as exc:
            raise ConfigurationError(
                "pre-action dependencies must be a non-empty iterable of FreshCtx objects or IDs"
            ) from exc
        if not dependencies:
            raise ConfigurationError("pre-action boundary requires at least one FreshCtx dependency")
        if store is None:
            raise ConfigurationError("pre-action boundary requires the store that owns its dependencies")
        self.dependencies = dependencies
        self.store = store
        self.policy = policy
        self.audit_path = audit_path
        self.validation_workers = validation_workers
        self.validation_budget_ms = validation_budget_ms
        self.retry_policy = retry_policy
        self.protected_parameters = protected_parameters
        self.parameter_values = parameter_values
        self.last_correlation = None

    @staticmethod
    def _metadata(call: PreActionCall) -> dict[str, str]:
        return {
            "contract": EXPERIMENTAL_PRE_ACTION_CONTRACT,
            "runtime": call.runtime,
            "action": call.action,
        }

    def invoke(
        self,
        call: PreActionCall,
        continuation: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Validate and invoke a synchronous framework continuation."""

        with guard(
            policy=self.policy,
            store=self.store,
            run_id=call.execution_id,
            audit_path=self.audit_path,
            validation_workers=self.validation_workers,
            validation_budget_ms=self.validation_budget_ms,
            retry_policy=self.retry_policy,
            action_attempt=ActionAttempt(call.operation_id,call.attempt_id,call.parent_attempt_id,call.previous_outcome) if any((call.operation_id,call.attempt_id,call.parent_attempt_id,call.previous_outcome)) else None,
        ) as ctx:
            with reasoning(
                "pre_action_integration",
                depends_on=self.dependencies,
                metadata=self._metadata(call),
            ) as boundary_decision:
                pass
            try:
                return ctx.run(
                    continuation,
                    *args,
                    depends_on=[boundary_decision],
                    boundary=call.boundary,
                    protected_parameters=self.protected_parameters,
                    parameter_values=self.parameter_values,
                    **kwargs,
                )
            finally:
                self.last_correlation = ctx.correlation

    async def invoke_async(
        self,
        call: PreActionCall,
        continuation: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Validate and invoke a synchronous or asynchronous continuation."""

        async with guard(
            policy=self.policy,
            store=self.store,
            run_id=call.execution_id,
            audit_path=self.audit_path,
            validation_workers=self.validation_workers,
            validation_budget_ms=self.validation_budget_ms,
            retry_policy=self.retry_policy,
            action_attempt=ActionAttempt(call.operation_id,call.attempt_id,call.parent_attempt_id,call.previous_outcome) if any((call.operation_id,call.attempt_id,call.parent_attempt_id,call.previous_outcome)) else None,
        ) as ctx:
            with reasoning(
                "pre_action_integration",
                depends_on=self.dependencies,
                metadata=self._metadata(call),
            ) as boundary_decision:
                pass
            try:
                return await ctx.run_async(
                    continuation,
                    *args,
                    depends_on=[boundary_decision],
                    boundary=call.boundary,
                    protected_parameters=self.protected_parameters,
                    parameter_values=self.parameter_values,
                    **kwargs,
                )
            finally:
                self.last_correlation = ctx.correlation
