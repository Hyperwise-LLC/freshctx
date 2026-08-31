"""Agno tool hooks that enforce a FreshCtx action boundary."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from os import PathLike
from typing import Any

from agno.exceptions import StopAgentRun

from ..core import FreshnessBlocked, guard
from ..errors import ConfigurationError


class FreshCtxAgnoBlocked(StopAgentRun):
    """Stop an Agno run after FreshCtx blocks its tool boundary."""

    def __init__(self, blocked: FreshnessBlocked):
        self.result = blocked.result
        super().__init__(blocked, agent_message=str(blocked))


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
) -> Callable[..., Any]:
    """Return a synchronous Agno tool hook protected by FreshCtx.

    Attach the returned hook to an Agno ``@tool`` or to an ``Agent``.  Agno
    passes the actual tool continuation as ``function_call``; FreshCtx validates
    the declared dependencies before invoking it.  A blocking FreshCtx result
    therefore prevents the tool body from running.
    """

    dependencies = _dependencies(depends_on)

    def freshctx_agno_hook(
        function_name: str,
        function_call: Callable[..., Any],
        arguments: Mapping[str, Any],
    ) -> Any:
        try:
            with guard(
                policy=policy,
                store=store,
                audit_path=audit_path,
                validation_workers=validation_workers,
                validation_budget_ms=validation_budget_ms,
            ) as ctx:
                return ctx.run(
                    function_call,
                    depends_on=dependencies,
                    boundary=f"agno.tool:{function_name}",
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
) -> Callable[..., Any]:
    """Return an asynchronous Agno tool hook protected by FreshCtx."""

    dependencies = _dependencies(depends_on)

    async def freshctx_agno_async_hook(
        function_name: str,
        function_call: Callable[..., Any],
        arguments: Mapping[str, Any],
    ) -> Any:
        try:
            async with guard(
                policy=policy,
                store=store,
                audit_path=audit_path,
                validation_workers=validation_workers,
                validation_budget_ms=validation_budget_ms,
            ) as ctx:
                return await ctx.run_async(
                    function_call,
                    depends_on=dependencies,
                    boundary=f"agno.tool:{function_name}",
                    **dict(arguments),
                )
        except FreshnessBlocked as blocked:
            raise FreshCtxAgnoBlocked(blocked) from blocked

    return freshctx_agno_async_hook
