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

from ..core import guard, reasoning
from ..errors import ConfigurationError


EXPERIMENTAL_PRE_ACTION_CONTRACT = "freshctx.pre_action.experimental.v1"


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

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, str) or not self.runtime.strip():
            raise ConfigurationError("pre-action runtime must not be empty")
        if not isinstance(self.action, str) or not self.action.strip():
            raise ConfigurationError("pre-action action must not be empty")
        if self.execution_id is not None and (
            not isinstance(self.execution_id, str) or not self.execution_id.strip()
        ):
            raise ConfigurationError("pre-action execution_id must not be empty")

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
        ) as ctx:
            with reasoning(
                "pre_action_integration",
                depends_on=self.dependencies,
                metadata=self._metadata(call),
            ) as boundary_decision:
                pass
            return ctx.run(
                continuation,
                *args,
                depends_on=[boundary_decision],
                boundary=call.boundary,
                **kwargs,
            )

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
        ) as ctx:
            with reasoning(
                "pre_action_integration",
                depends_on=self.dependencies,
                metadata=self._metadata(call),
            ) as boundary_decision:
                pass
            return await ctx.run_async(
                continuation,
                *args,
                depends_on=[boundary_decision],
                boundary=call.boundary,
                **kwargs,
            )
