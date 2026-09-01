"""Experimental LangGraph mapping for the FreshCtx pre-action contract."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from os import PathLike
from typing import Any

from ..errors import ConfigurationError
from .pre_action import PreActionBoundary, PreActionCall


DependencySource = Iterable[Any] | Callable[[Any], Iterable[Any]]
ExecutionIdSource = str | Callable[[Any], str | None] | None


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
) -> Callable[[Any], Any]:
    """Wrap a synchronous LangGraph action node with a pre-action boundary.

    ``depends_on`` may be a fixed iterable or a resolver that reads FreshCtx
    dependency identifiers from graph state. The action receives the original
    state only after FreshCtx permits execution.
    """

    name = _action_name(action, action_name)

    @wraps(action)
    def freshctx_langgraph_action(state: Any) -> Any:
        boundary = PreActionBoundary(
            depends_on=_dependencies(depends_on, state),
            store=store,
            policy=policy,
            audit_path=audit_path,
            validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms,
        )
        return boundary.invoke(
            PreActionCall(
                runtime="langgraph",
                action=name,
                execution_id=_execution_id(execution_id, state),
            ),
            action,
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
) -> Callable[[Any], Any]:
    """Wrap an asynchronous LangGraph action node with the same contract."""

    name = _action_name(action, action_name)

    @wraps(action)
    async def freshctx_langgraph_async_action(state: Any) -> Any:
        boundary = PreActionBoundary(
            depends_on=_dependencies(depends_on, state),
            store=store,
            policy=policy,
            audit_path=audit_path,
            validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms,
        )
        return await boundary.invoke_async(
            PreActionCall(
                runtime="langgraph",
                action=name,
                execution_id=_execution_id(execution_id, state),
            ),
            action,
            state,
        )

    return freshctx_langgraph_async_action
