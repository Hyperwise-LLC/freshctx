"""Official MCP Python SDK v2 tool-call guard backed by FreshCtx."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from os import PathLike
from typing import Any

from ..core import FreshnessBlocked, parameter_digest, reasoning
from ..errors import ConfigurationError
from ..model import ActionAttempt, ProtectedParameter, RetryPolicy
from .pre_action import EXPERIMENTAL_PRE_ACTION_CONTRACT, PreActionBoundary, PreActionCall

try:
    from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
    from mcp.server.extension import Extension
    from mcp.types import CallToolRequestParams, CallToolResult, TextContent
except ImportError as exc:  # pragma: no cover - exercised by package smoke tests
    raise ImportError("install freshctx[mcp-guard] to use FreshCtxMCPGuard") from exc


DependencyResolver = Callable[[str], Iterable[Any]]
DependencySource = Iterable[Any] | Mapping[str, Iterable[Any]] | DependencyResolver
MCP_GUARD_RESULT_SCHEMA = "freshctx.mcp_guard.result.v1"


def _dependency_tuple(value: Iterable[Any], *, tool_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise ConfigurationError(
            f"MCP Guard dependencies for {tool_name!r} must be a non-empty iterable of FreshCtx objects or IDs"
        )
    try:
        dependencies = tuple(value)
    except TypeError as exc:
        raise ConfigurationError(
            f"MCP Guard dependencies for {tool_name!r} must be a non-empty iterable of FreshCtx objects or IDs"
        ) from exc
    if not dependencies:
        raise ConfigurationError(f"MCP Guard requires at least one FreshCtx dependency for {tool_name!r}")
    return dependencies


def _tool_names(configured: Iterable[str] | None) -> frozenset[str] | None:
    if configured is None:
        return None
    if isinstance(configured, (str, bytes)):
        raise ConfigurationError("MCP Guard protected_tools must be an iterable of non-empty names")
    try:
        names = frozenset(configured)
    except TypeError as exc:
        raise ConfigurationError("MCP Guard protected_tools must be an iterable of non-empty names") from exc
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ConfigurationError("MCP Guard protected_tools must contain at least one non-empty name")
    return names


class FreshCtxMCPGuard(Extension):
    """Veto protected MCP ``tools/call`` requests before tool execution.

    The guard is an opt-in MCP Python SDK v2 server extension. ``depends_on``
    may be a fixed dependency set, a mapping keyed by tool name, or a resolver
    that receives only the tool name. MCP tool arguments are deliberately not
    exposed to the resolver or copied into FreshCtx metadata.
    """

    identifier = "com.freshctx/action-boundary"

    def __init__(
        self,
        *,
        depends_on: DependencySource,
        store: Any,
        protected_tools: Iterable[str] | None = None,
        policy: str = "block",
        audit_path: str | PathLike[str] = ".freshctx/mcp-guard-audit.jsonl",
        validation_workers: int = 1,
        validation_budget_ms: float | None = None,
        retry_policy: RetryPolicy | None = None,
        protected_parameters: Mapping[str, ProtectedParameter] | None = None,
        action_attempt: ActionAttempt | None = None,
        output_lineage: Callable[[str, Any], tuple[str, Iterable[Any]]] | None = None,
        on_output_node: Callable[[Any], None] | None = None,
    ) -> None:
        if store is None:
            raise ConfigurationError("MCP Guard requires the store that owns its dependencies")
        self.store = store
        self.policy = policy
        self.audit_path = audit_path
        self.validation_workers = validation_workers
        self.validation_budget_ms = validation_budget_ms
        self.retry_policy = retry_policy
        self.protected_parameters = dict(protected_parameters) if protected_parameters is not None else None
        self.action_attempt = action_attempt
        if (output_lineage is None) != (on_output_node is None):
            raise ConfigurationError("MCP Guard output_lineage and on_output_node must be supplied together")
        self.output_lineage = output_lineage
        self.on_output_node = on_output_node
        self.protected_tools = _tool_names(protected_tools)

        if isinstance(depends_on, Mapping):
            if not depends_on:
                raise ConfigurationError("MCP Guard dependency mapping must not be empty")
            self._dependency_source: DependencySource = {
                name: _dependency_tuple(value, tool_name=name)
                for name, value in depends_on.items()
                if isinstance(name, str) and name.strip()
            }
            if len(self._dependency_source) != len(depends_on):
                raise ConfigurationError("MCP Guard dependency mapping keys must be non-empty tool names")
        elif callable(depends_on):
            self._dependency_source = depends_on
        else:
            self._dependency_source = _dependency_tuple(depends_on, tool_name="*")

    def settings(self) -> dict[str, Any]:
        return {
            "contract": EXPERIMENTAL_PRE_ACTION_CONTRACT,
            "failClosed": self.policy == "block",
        }

    def _dependencies(self, tool_name: str) -> tuple[Any, ...]:
        source = self._dependency_source
        if isinstance(source, Mapping):
            if tool_name not in source:
                raise ConfigurationError(f"MCP Guard has no declared dependencies for protected tool {tool_name!r}")
            value = source[tool_name]
        elif callable(source):
            value = source(tool_name)
        else:
            value = source
        return _dependency_tuple(value, tool_name=tool_name)

    async def intercept_tool_call(
        self,
        params: CallToolRequestParams,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        tool_name = params.name
        if self.protected_tools is not None and tool_name not in self.protected_tools:
            return await call_next(ctx)

        boundary = PreActionBoundary(
            depends_on=self._dependencies(tool_name),
            store=self.store,
            policy=self.policy,
            audit_path=self.audit_path,
            validation_workers=self.validation_workers,
            validation_budget_ms=self.validation_budget_ms,
            retry_policy=self.retry_policy,
            protected_parameters=self.protected_parameters,
            parameter_values=(
                {name: (params.arguments or {})[name] for name in self.protected_parameters if name in (params.arguments or {})}
                if self.protected_parameters is not None else None
            ),
        )
        request_id = getattr(ctx, "request_id", None)
        execution_id = str(request_id) if request_id is not None else None
        async def continuation(context: Any) -> HandlerResult:
            result = await call_next(context)
            if self.output_lineage is not None and self.on_output_node is not None:
                invocation_id, dependencies = self.output_lineage(tool_name, result)
                if not isinstance(invocation_id, str) or not invocation_id.strip():
                    raise ConfigurationError("MCP Guard output lineage requires a stable invocation ID")
                dump = getattr(result, "model_dump", None)
                digest_value = dump(mode="json") if callable(dump) else result
                with reasoning(
                    "tool_output", depends_on=dependencies,
                    metadata={"tool_invocation_id": invocation_id, "output_digest": parameter_digest(digest_value)},
                ) as output_node:
                    pass
                self.on_output_node(output_node)
            return result
        try:
            return await boundary.invoke_async(
                PreActionCall(
                    runtime="mcp", action=tool_name, execution_id=execution_id,
                    operation_id=self.action_attempt.operation_id if self.action_attempt else None,
                    attempt_id=self.action_attempt.attempt_id if self.action_attempt else None,
                    parent_attempt_id=self.action_attempt.parent_attempt_id if self.action_attempt else None,
                    previous_outcome=self.action_attempt.previous_outcome if self.action_attempt else None,
                ),
                continuation,
                ctx,
            )
        except FreshnessBlocked as blocked:
            result = blocked.result.to_dict()
            correlation = blocked.correlation.to_dict() if blocked.correlation is not None else None
            state = result["state"]
            public_result = {
                "schemaVersion": MCP_GUARD_RESULT_SCHEMA,
                "status": "blocked",
                "reason": "freshctx_pre_action_blocked",
                "tool": tool_name,
                "state": state,
                "policyDecision": result["policy_decision"],
                "correlationId": correlation["correlation_id"] if correlation is not None else None,
                "executionId": execution_id,
            }
            return CallToolResult.model_validate(
                {
                    "content": [
                        TextContent(
                            type="text",
                            text=f"FreshCtx blocked {tool_name}: declared evidence is {state}.",
                        )
                    ],
                    "structuredContent": public_result,
                    "isError": True,
                    "_meta": {
                        "com.freshctx/result": result,
                        "com.freshctx/correlation": correlation,
                        "com.freshctx/contract": EXPERIMENTAL_PRE_ACTION_CONTRACT,
                        "com.freshctx/resultSchema": MCP_GUARD_RESULT_SCHEMA,
                    },
                }
            )
