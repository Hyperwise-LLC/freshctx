"""Experimental LangGraph mapping for the FreshCtx pre-action contract."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from os import PathLike
from typing import Any

from ..core import parameter_digest, reasoning
from ..errors import ConfigurationError
from ..model import ActionAttempt, ProtectedParameter, RetryPolicy
from .pre_action import PreActionBoundary, PreActionCall


DependencySource = Iterable[Any] | Callable[[Any], Iterable[Any]]
ExecutionIdSource = str | Callable[[Any], str | None] | None
ParameterValueSource = Callable[[Any], dict[str, Any]] | None
ActionAttemptSource = ActionAttempt | Callable[[Any], ActionAttempt | None] | None
OutputLineageSource = Callable[[Any, Any], tuple[str, Iterable[Any]]]
OutputNodeSink = Callable[[Any], None]


def _action_name(action: Callable[..., Any], configured: str | None) -> str:
    if not callable(action):
        raise ConfigurationError("LangGraph action node must be callable")
    name = configured or getattr(action, "__name__", type(action).__name__)
    if not str(name).strip():
        raise ConfigurationError("LangGraph action_name must not be empty")
    return str(name)


def _dependencies(source: DependencySource, state: Any) -> tuple[Any, ...]:
    resolved = source(state) if callable(source) else source
    if isinstance(resolved, (str, bytes)):
        raise ConfigurationError("LangGraph dependencies must be a non-empty iterable of FreshCtx objects or IDs")
    try:
        dependencies = tuple(resolved)
    except TypeError as exc:
        raise ConfigurationError(
            "LangGraph dependencies must be a non-empty iterable of FreshCtx objects or IDs"
        ) from exc
    if not dependencies:
        raise ConfigurationError("LangGraph action node requires at least one FreshCtx dependency")
    return dependencies


def _execution_id(source: ExecutionIdSource, state: Any) -> str | None:
    resolved = source(state) if callable(source) else source
    if resolved is not None and (not isinstance(resolved, str) or not resolved.strip()):
        raise ConfigurationError("LangGraph execution_id must resolve to a non-empty string or None")
    return resolved


def _attempt(source: ActionAttemptSource, state: Any) -> ActionAttempt | None:
    result = source(state) if callable(source) else source
    if result is not None and not isinstance(result, ActionAttempt):
        raise ConfigurationError("LangGraph action_attempt must resolve to ActionAttempt or None")
    return result


def _record_output(state: Any, result: Any, source: OutputLineageSource, sink: OutputNodeSink) -> None:
    invocation_id, dependencies = source(state, result)
    if not isinstance(invocation_id, str) or not invocation_id.strip():
        raise ConfigurationError("LangGraph output lineage requires a stable invocation ID")
    with reasoning(
        "tool_output", depends_on=dependencies,
        metadata={"tool_invocation_id": invocation_id, "output_digest": parameter_digest(result)},
    ) as output_node:
        pass
    sink(output_node)


def langgraph_action_node(
    action: Callable[[Any], Any],
    *,
    depends_on: DependencySource,
    store: Any,
    action_name: str | None = None,
    execution_id: ExecutionIdSource = None,
    policy: str = "block",
    audit_path: str | PathLike[str] = ".freshctx/langgraph-audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
    retry_policy: RetryPolicy | None = None,
    protected_parameters: dict[str, ProtectedParameter] | None = None,
    parameter_values: ParameterValueSource = None,
    action_attempt: ActionAttemptSource = None,
    output_lineage: OutputLineageSource | None = None,
    on_output_node: OutputNodeSink | None = None,
) -> Callable[[Any], Any]:
    """Wrap a synchronous LangGraph action node with a pre-action boundary.

    ``depends_on`` may be a fixed iterable or a resolver that reads FreshCtx
    dependency identifiers from graph state. The action receives the original
    state only after FreshCtx permits execution.
    """

    name = _action_name(action, action_name)
    if (output_lineage is None) != (on_output_node is None):
        raise ConfigurationError("LangGraph output_lineage and on_output_node must be supplied together")

    def continuation(state: Any) -> Any:
        result = action(state)
        if output_lineage is not None and on_output_node is not None:
            _record_output(state, result, output_lineage, on_output_node)
        return result

    @wraps(action)
    def freshctx_langgraph_action(state: Any) -> Any:
        attempt = _attempt(action_attempt, state)
        boundary = PreActionBoundary(
            depends_on=_dependencies(depends_on, state),
            store=store,
            policy=policy,
            audit_path=audit_path,
            validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms,
            retry_policy=retry_policy,
            protected_parameters=protected_parameters,
            parameter_values=parameter_values(state) if parameter_values is not None else None,
        )
        return boundary.invoke(
            PreActionCall(
                runtime="langgraph",
                action=name,
                execution_id=_execution_id(execution_id, state),
                operation_id=attempt.operation_id if attempt else None,
                attempt_id=attempt.attempt_id if attempt else None,
                parent_attempt_id=attempt.parent_attempt_id if attempt else None,
                previous_outcome=attempt.previous_outcome if attempt else None,
            ),
            continuation,
            state,
        )

    return freshctx_langgraph_action


def langgraph_async_action_node(
    action: Callable[[Any], Any],
    *,
    depends_on: DependencySource,
    store: Any,
    action_name: str | None = None,
    execution_id: ExecutionIdSource = None,
    policy: str = "block",
    audit_path: str | PathLike[str] = ".freshctx/langgraph-audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
    retry_policy: RetryPolicy | None = None,
    protected_parameters: dict[str, ProtectedParameter] | None = None,
    parameter_values: ParameterValueSource = None,
    action_attempt: ActionAttemptSource = None,
    output_lineage: OutputLineageSource | None = None,
    on_output_node: OutputNodeSink | None = None,
) -> Callable[[Any], Any]:
    """Wrap an asynchronous LangGraph action node with the same contract."""

    name = _action_name(action, action_name)
    if (output_lineage is None) != (on_output_node is None):
        raise ConfigurationError("LangGraph output_lineage and on_output_node must be supplied together")

    async def continuation(state: Any) -> Any:
        result = await action(state)
        if output_lineage is not None and on_output_node is not None:
            _record_output(state, result, output_lineage, on_output_node)
        return result

    @wraps(action)
    async def freshctx_langgraph_async_action(state: Any) -> Any:
        attempt = _attempt(action_attempt, state)
        boundary = PreActionBoundary(
            depends_on=_dependencies(depends_on, state),
            store=store,
            policy=policy,
            audit_path=audit_path,
            validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms,
            retry_policy=retry_policy,
            protected_parameters=protected_parameters,
            parameter_values=parameter_values(state) if parameter_values is not None else None,
        )
        return await boundary.invoke_async(
            PreActionCall(
                runtime="langgraph",
                action=name,
                execution_id=_execution_id(execution_id, state),
                operation_id=attempt.operation_id if attempt else None,
                attempt_id=attempt.attempt_id if attempt else None,
                parent_attempt_id=attempt.parent_attempt_id if attempt else None,
                previous_outcome=attempt.previous_outcome if attempt else None,
            ),
            continuation,
            state,
        )

    return freshctx_langgraph_async_action
