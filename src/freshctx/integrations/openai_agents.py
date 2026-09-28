"""OpenAI Agents SDK function-tool guardrails backed by FreshCtx."""

from __future__ import annotations

from collections.abc import Iterable
import json
from os import PathLike
from typing import Any

from agents.tool_guardrails import (
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
    tool_input_guardrail,
)

from ..core import FreshnessBlocked
from ..errors import ConfigurationError
from ..model import ActionAttempt, ProtectedParameter, RetryPolicy
from .pre_action import (
    EXPERIMENTAL_PRE_ACTION_CONTRACT,
    PreActionBoundary,
    PreActionCall,
    blocked_contract_payload,
)


def _dependencies(depends_on: Iterable[Any]) -> tuple[Any, ...]:
    if isinstance(depends_on, (str, bytes)):
        raise ConfigurationError(
            "OpenAI Agents SDK guardrail dependencies must be a non-empty iterable of FreshCtx objects or IDs"
        )
    try:
        dependencies = tuple(depends_on)
    except TypeError as exc:
        raise ConfigurationError(
            "OpenAI Agents SDK guardrail dependencies must be a non-empty iterable of FreshCtx objects or IDs"
        ) from exc
    if not dependencies:
        raise ConfigurationError("OpenAI Agents SDK guardrail requires at least one FreshCtx dependency")
    return dependencies


def openai_agents_tool_guardrail(
    *,
    depends_on: Iterable[Any],
    store: Any,
    policy: str = "block",
    audit_path: str | PathLike[str] = ".freshctx/openai-agents-audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
    retry_policy: RetryPolicy | None = None,
    protected_parameters: dict[str, ProtectedParameter] | None = None,
    action_attempt: ActionAttempt | None = None,
) -> ToolInputGuardrail[Any]:
    """Return an SDK input guardrail for a protected function tool."""

    dependencies = _dependencies(depends_on)

    @tool_input_guardrail(name="freshctx_pre_action")
    async def freshctx_openai_agents_guardrail(
        data: ToolInputGuardrailData,
    ) -> ToolGuardrailFunctionOutput:
        values: dict[str, Any] | None = None
        if protected_parameters is not None:
            try:
                arguments = json.loads(data.context.tool_arguments)
            except (TypeError, ValueError):
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            values = {name: arguments[name] for name in protected_parameters if name in arguments}
        boundary = PreActionBoundary(
            depends_on=dependencies, store=store, policy=policy,
            audit_path=audit_path, validation_workers=validation_workers,
            validation_budget_ms=validation_budget_ms, retry_policy=retry_policy,
            protected_parameters=protected_parameters, parameter_values=values,
        )
        call = PreActionCall(
            runtime="openai_agents",
            action=data.context.qualified_tool_name,
            execution_id=data.context.tool_call_id,
            operation_id=action_attempt.operation_id if action_attempt else None,
            attempt_id=action_attempt.attempt_id if action_attempt else None,
            parent_attempt_id=action_attempt.parent_attempt_id if action_attempt else None,
            previous_outcome=action_attempt.previous_outcome if action_attempt else None,
        )
        try:
            await boundary.invoke_async(call, lambda: None)
        except FreshnessBlocked as blocked:
            return ToolGuardrailFunctionOutput.raise_exception(blocked_contract_payload(blocked))
        return ToolGuardrailFunctionOutput.allow(
            {
                "freshctx": {"state": "CURRENT", "policy_decision": "allow"},
                "contract": EXPERIMENTAL_PRE_ACTION_CONTRACT,
            }
        )

    return freshctx_openai_agents_guardrail
