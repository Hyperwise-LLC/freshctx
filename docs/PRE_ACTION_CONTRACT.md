# Experimental pre-action integration contract

Status: experimental, not part of the stable FreshCtx API
Contract identifier: `freshctx.pre_action.experimental.v1`

## Purpose

The contract gives framework bridges one narrow job: place the same FreshCtx validation boundary immediately before the framework invokes a consequential action. It is being tested across Agno, LangGraph, OpenAI Agents SDK, and Google ADK before FreshCtx considers a stable public integration API.

## Invariant

For every protected framework action:

1. The application preserves the FreshCtx store and dependency IDs created during observation and reasoning.
2. The bridge identifies the runtime and action without copying tool arguments into FreshCtx metadata.
3. FreshCtx evaluates the declared dependencies immediately before the real framework continuation.
4. A blocking result prevents the continuation from starting.
5. A permitted result records `action_allowed` before the continuation starts.
6. The framework retains ownership of tool selection, retries, handoffs, streaming, transactions, idempotency, and lifecycle state.

## Experimental Python surface

```python
from freshctx.integrations.pre_action import PreActionBoundary, PreActionCall

boundary = PreActionBoundary(
    depends_on=[decision],
    store=store,
    policy="block",
)

result = boundary.invoke(
    PreActionCall(
        runtime="example-runtime",
        action="write_record",
        execution_id="framework-run-123",
    ),
    real_framework_continuation,
    record_id,
)
```

Use `await boundary.invoke_async(...)` for an asynchronous continuation. The async method also accepts a synchronous continuation when a framework exposes a mixed execution path.

## Required mapping from a framework

| Contract concept | Framework bridge responsibility |
|---|---|
| `runtime` | Stable lowercase framework identifier, such as `agno` or `langgraph`. |
| `action` | Tool or action name visible to developers and audit consumers. |
| `execution_id` | Optional framework run/call correlation ID. It becomes the FreshCtx audit run ID. |
| `depends_on` | Non-empty FreshCtx token or reasoning identifiers owned by the application's store. |
| `continuation` | The framework's real next callable. It must not be invoked before FreshCtx permits it. |
| arguments | Passed directly to the continuation; never copied into contract metadata. |
| blocked result | Translated into the framework's supported stop/failure mechanism without invoking the continuation. |

## Result semantics

The contract does not invent framework-specific freshness states. It preserves FreshCtx states and policy decisions:

- `CURRENT` may proceed.
- `STALE_SOURCE`, `STALE_REASONING`, and `UNVERIFIABLE` follow the configured policy.
- Blocking policies raise `FreshnessBlocked` before the continuation starts.
- Framework bridges may translate that exception, but must preserve its `CheckResult`.
- `REPLAN` and `REQUIRE_APPROVAL` remain application responses; FreshCtx does not perform either operation automatically.

## Security and data handling

- Tool arguments and business payloads are deliberately not members of `PreActionCall`.
- The contract persists only its version, runtime identifier, action identifier, dependency graph, and normal FreshCtx evidence.
- Framework credentials remain in the framework or adapter process and must not be placed in metadata.
- A missing store, empty dependency set, or incomplete validation fails before action execution.

## Conformance requirements

A framework integration is not considered conformant until installed-framework tests prove:

1. Current evidence invokes the real action exactly once.
2. Stale evidence prevents the action body from starting.
3. Unverifiable evidence follows the configured fail-closed policy.
4. Sync and async execution are covered when the framework supports them.
5. The framework's blocking exception retains the FreshCtx result.
6. Audit evidence identifies the runtime, action, contract version, and framework execution ID when supplied.
7. Arguments and credentials are absent from FreshCtx integration metadata.
8. The documentation states which lifecycle responsibilities remain outside FreshCtx.

## Current evidence

The Agno 2.9 hook consumes this contract and retains its existing public API and framework-specific `FreshCtxAgnoBlocked` translation. LangGraph is the second mapping: synchronous and asynchronous action-node wrappers resolve dependencies from graph state, correlate an optional graph execution ID, and propagate `FreshnessBlocked` before the node body begins. OpenAI Agents SDK is the third mapping: a function-tool input guardrail correlates the SDK tool-call ID, records the tool name without its arguments, and translates blocking results into the SDK's native input-tool tripwire before the function body starts.

## Stability rule

Do not export this module from `freshctx` or `freshctx.integrations`, promise semantic-version stability, or use it as a marketing compatibility claim yet. Stabilization requires successful mappings for Agno, hardened LangGraph, OpenAI Agents SDK, and Google ADK, followed by a comparison of the four implementations.
