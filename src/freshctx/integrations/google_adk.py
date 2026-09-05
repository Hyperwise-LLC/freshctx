"""Google Agent Development Kit tool callbacks backed by FreshCtx."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from os import PathLike
from typing import Any

from ..core import FreshnessBlocked
from ..errors import ConfigurationError
from .pre_action import (
    PreActionBoundary,
    PreActionCall,
    blocked_contract_payload,
)


DependencySource = Iterable[Any] | Callable[[Any, Any], Iterable[Any]]


def _dependencies(source: DependencySource, tool: Any, tool_context: Any) -> tuple[Any, ...]:
    resolved = source(tool, tool_context) if callable(source) else source
    if isinstance(resolved, (str, bytes)):
        raise ConfigurationError(
            "Google ADK dependencies must be a non-empty iterable of FreshCtx objects or IDs"
        )
    try:
        dependencies = tuple(resolved)
    except TypeError as exc:
        raise ConfigurationError(
            "Google ADK dependencies must be a non-empty iterable of FreshCtx objects or IDs"
        ) from exc
    if not dependencies:
        raise ConfigurationError("Google ADK tool callback requires at least one FreshCtx dependency")
    return dependencies


def _tool_names(configured: Iterable[str] | None) -> frozenset[str] | None:
    if configured is None:
        return None
    if isinstance(configured, (str, bytes)):
        raise ConfigurationError("Google ADK tool_names must be an iterable of non-empty names")
    try:
        names = frozenset(configured)
    except TypeError as exc:
        raise ConfigurationError("Google ADK tool_names must be an iterable of non-empty names") from exc
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ConfigurationError("Google ADK tool_names must contain at least one non-empty name")
    return names


def google_adk_tool_callback(
    *,
    depends_on: DependencySource,
    store: Any,
    tool_names: Iterable[str] | None = None,
    policy: str = "block",
    audit_path: str | PathLike[str] = ".freshctx/google-adk-audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
) -> Callable[..., Any]:
    """Return an async ``before_tool_callback`` for a Google ADK agent.

    Returning a dictionary from an ADK before-tool callback skips the tool
    body. FreshCtx uses that native override path for blocking decisions and
    returns ``None`` only when the protected action may proceed. ``depends_on``
    may be a fixed iterable or a resolver receiving ``(tool, tool_context)``.
    Tool arguments are deliberately excluded from the resolver and FreshCtx
    audit metadata.
    """

    selected_tools = _tool_names(tool_names)
    if store is None:
        raise ConfigurationError("Google ADK tool callback requires the store that owns its dependencies")
    if not callable(depends_on):
        fixed_dependencies = _dependencies(depends_on, None, None)
        dependency_source: DependencySource = fixed_dependencies
    else:
        dependency_source = depends_on

    async def freshctx_google_adk_before_tool(*, tool: Any, args: dict[str, Any], tool_context: Any):
        del args
        action = getattr(tool, "name", None)
        if not isinstance(action, str) or not action.strip():
            raise ConfigurationError("Google ADK tool must expose a non-empty name")
        if selected_tools is not None and action not in selected_tools:
            return None

        boundary = PreActionBoundary(
            depends_on=_dependencies(dependency_source, tool, tool_context),
            store=store,
            policy=policy,
            audit_path=audit_path,
            validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms,
        )
        call_id = getattr(tool_context, "function_call_id", None)
        if call_id is not None:
            call_id = str(call_id)
        try:
            await boundary.invoke_async(
                PreActionCall(runtime="google_adk", action=action, execution_id=call_id),
                lambda: None,
            )
        except FreshnessBlocked as blocked:
            return {
                "status": "blocked",
                "error": "freshctx_pre_action_blocked",
                **blocked_contract_payload(blocked),
            }
        return None

    return freshctx_google_adk_before_tool
