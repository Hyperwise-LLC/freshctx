"""ElevenLabs client-tool registration protected by FreshCtx."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from os import PathLike
from typing import Any

from ..core import FreshnessBlocked
from ..errors import ConfigurationError
from .pre_action import PreActionBoundary, PreActionCall, blocked_contract_payload


def _dependencies(depends_on: Iterable[Any]) -> tuple[Any, ...]:
    if isinstance(depends_on, (str, bytes)):
        raise ConfigurationError(
            "ElevenLabs client-tool dependencies must be a non-empty iterable"
        )
    try:
        dependencies = tuple(depends_on)
    except TypeError as exc:
        raise ConfigurationError(
            "ElevenLabs client-tool dependencies must be a non-empty iterable"
        ) from exc
    if not dependencies:
        raise ConfigurationError(
            "ElevenLabs client tool requires at least one FreshCtx dependency"
        )
    return dependencies


def _action_name(tool_name: str) -> str:
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ConfigurationError("ElevenLabs client-tool name must not be empty")
    return tool_name.strip()


def _blocked_response(blocked: FreshnessBlocked) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error": "freshctx_pre_action_blocked",
        **blocked_contract_payload(blocked),
    }


def register_elevenlabs_client_tool(
    client_tools: Any,
    tool_name: str,
    handler: Callable[[Mapping[str, Any]], Any],
    *,
    depends_on: Iterable[Any],
    store: Any,
    is_async: bool = False,
    policy: str = "block",
    audit_path: str | PathLike[str] = ".freshctx/elevenlabs-audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
) -> Callable[[dict[str, Any]], Any]:
    """Register one protected ElevenLabs Python SDK client tool.

    ElevenLabs passes all tool parameters to the returned handler. FreshCtx
    passes them directly to the application continuation but deliberately does
    not copy them into its objects or audit metadata. The application should
    configure the ElevenLabs tool to wait for its response.
    """

    action = _action_name(tool_name)
    if store is None:
        raise ConfigurationError(
            "ElevenLabs client tool requires the store that owns its dependencies"
        )
    if not callable(handler):
        raise ConfigurationError("ElevenLabs client-tool handler must be callable")
    register = getattr(client_tools, "register", None)
    if not callable(register):
        raise ConfigurationError("client_tools must expose a callable register method")

    boundary = PreActionBoundary(
        depends_on=_dependencies(depends_on),
        store=store,
        policy=policy,
        audit_path=audit_path,
        validation_workers=validation_workers,
        validation_budget_ms=validation_budget_ms,
    )

    protected_handler: Callable[[dict[str, Any]], Any]
    if is_async:
        async def protected_async(parameters: dict[str, Any]) -> Any:
            try:
                return await boundary.invoke_async(
                    PreActionCall(runtime="elevenlabs", action=action),
                    handler,
                    parameters,
                )
            except FreshnessBlocked as blocked:
                return _blocked_response(blocked)
        protected_handler = protected_async
    else:
        def protected_sync(parameters: dict[str, Any]) -> Any:
            try:
                return boundary.invoke(
                    PreActionCall(runtime="elevenlabs", action=action),
                    handler,
                    parameters,
                )
            except FreshnessBlocked as blocked:
                return _blocked_response(blocked)
        protected_handler = protected_sync

    register(action, protected_handler, is_async=is_async)
    return protected_handler
