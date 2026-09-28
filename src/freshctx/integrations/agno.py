"""Agno tool hooks that enforce a FreshCtx action boundary."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from os import PathLike
from typing import Any

from agno.exceptions import StopAgentRun

from ..core import FreshnessBlocked, parameter_digest, reasoning
from ..errors import ConfigurationError
from ..model import ActionAttempt, ProtectedParameter, RetryPolicy
from .pre_action import PreActionBoundary, PreActionCall


class FreshCtxAgnoBlocked(StopAgentRun):
    """Stop an Agno run after FreshCtx blocks its tool boundary."""

    def __init__(self, blocked: FreshnessBlocked):
        self.result = blocked.result
        self.correlation = blocked.correlation
        super().__init__(blocked, agent_message=str(blocked))


def _record_output(function_name: str, arguments: Mapping[str, Any], result: Any, source: Any, sink: Any) -> None:
    invocation_id, dependencies = source(function_name, arguments, result)
    if not isinstance(invocation_id, str) or not invocation_id.strip():
        raise ConfigurationError("Agno output lineage requires a stable invocation ID")
    with reasoning(
        "tool_output", depends_on=dependencies,
        metadata={"tool_invocation_id": invocation_id, "output_digest": parameter_digest(result)},
    ) as output_node:
        pass
    sink(output_node)


def _dependencies(depends_on: Iterable[Any]) -> tuple[Any, ...]:
    dependencies = tuple(depends_on)
    if not dependencies:
        raise ConfigurationError("Agno tool hook requires at least one FreshCtx dependency")
    return dependencies


def agno_tool_hook(
    *,
    depends_on: Iterable[Any],
    store: Any,
    policy: str = "block",
    audit_path: str | PathLike[str] = ".freshctx/agno-audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
    retry_policy: RetryPolicy | None = None,
    protected_parameters: dict[str, ProtectedParameter] | None = None,
    action_attempt: ActionAttempt | None = None,
    output_lineage: Callable[[str, Mapping[str, Any], Any], tuple[str, Iterable[Any]]] | None = None,
    on_output_node: Callable[[Any], None] | None = None,
) -> Callable[..., Any]:
    """Return a synchronous Agno tool hook protected by FreshCtx.

    Attach the returned hook to an Agno ``@tool`` or to an ``Agent``.  Agno
    passes the actual tool continuation as ``function_call``; FreshCtx validates
    the declared dependencies before invoking it.  A blocking FreshCtx result
    therefore prevents the tool body from running.
    """

    dependencies = _dependencies(depends_on)
    if (output_lineage is None) != (on_output_node is None):
        raise ConfigurationError("Agno output_lineage and on_output_node must be supplied together")

    def freshctx_agno_hook(
        function_name: str,
        function_call: Callable[..., Any],
        arguments: Mapping[str, Any],
    ) -> Any:
        def continuation(**values: Any) -> Any:
            result = function_call(**values)
            if output_lineage is not None and on_output_node is not None:
                _record_output(function_name, arguments, result, output_lineage, on_output_node)
            return result

        boundary = PreActionBoundary(
            depends_on=dependencies, store=store, policy=policy,
            audit_path=audit_path, validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms, retry_policy=retry_policy,
            protected_parameters=protected_parameters,
            parameter_values=(
                {name: arguments[name] for name in protected_parameters if name in arguments}
                if protected_parameters is not None else None
            ),
        )
        try:
            return boundary.invoke(
                PreActionCall(
                    runtime="agno", action=function_name,
                    operation_id=action_attempt.operation_id if action_attempt else None,
                    attempt_id=action_attempt.attempt_id if action_attempt else None,
                    parent_attempt_id=action_attempt.parent_attempt_id if action_attempt else None,
                    previous_outcome=action_attempt.previous_outcome if action_attempt else None,
                ),
                continuation,
                **dict(arguments),
            )
        except FreshnessBlocked as blocked:
            raise FreshCtxAgnoBlocked(blocked) from blocked

    return freshctx_agno_hook


def agno_async_tool_hook(
    *,
    depends_on: Iterable[Any],
    store: Any,
    policy: str = "block",
    audit_path: str | PathLike[str] = ".freshctx/agno-audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
    retry_policy: RetryPolicy | None = None,
    protected_parameters: dict[str, ProtectedParameter] | None = None,
    action_attempt: ActionAttempt | None = None,
    output_lineage: Callable[[str, Mapping[str, Any], Any], tuple[str, Iterable[Any]]] | None = None,
    on_output_node: Callable[[Any], None] | None = None,
) -> Callable[..., Any]:
    """Return an asynchronous Agno tool hook protected by FreshCtx."""

    dependencies = _dependencies(depends_on)
    if (output_lineage is None) != (on_output_node is None):
        raise ConfigurationError("Agno output_lineage and on_output_node must be supplied together")

    async def freshctx_agno_async_hook(
        function_name: str,
        function_call: Callable[..., Any],
        arguments: Mapping[str, Any],
    ) -> Any:
        async def continuation(**values: Any) -> Any:
            result = await function_call(**values)
            if output_lineage is not None and on_output_node is not None:
                _record_output(function_name, arguments, result, output_lineage, on_output_node)
            return result

        boundary = PreActionBoundary(
            depends_on=dependencies, store=store, policy=policy,
            audit_path=audit_path, validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms, retry_policy=retry_policy,
            protected_parameters=protected_parameters,
            parameter_values=(
                {name: arguments[name] for name in protected_parameters if name in arguments}
                if protected_parameters is not None else None
            ),
        )
        try:
            return await boundary.invoke_async(
                PreActionCall(
                    runtime="agno", action=function_name,
                    operation_id=action_attempt.operation_id if action_attempt else None,
                    attempt_id=action_attempt.attempt_id if action_attempt else None,
                    parent_attempt_id=action_attempt.parent_attempt_id if action_attempt else None,
                    previous_outcome=action_attempt.previous_outcome if action_attempt else None,
                ),
                continuation,
                **dict(arguments),
            )
        except FreshnessBlocked as blocked:
            raise FreshCtxAgnoBlocked(blocked) from blocked

    return freshctx_agno_async_hook
