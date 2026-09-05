# Cross-integration action/evidence correlation

FreshCtx emits the same `freshctx.action_evidence_correlation.v1` record at
every supported pre-action boundary. The framework entry point changes; the
evidence-to-action trace does not.

## Supported boundaries

| Runtime | Native boundary | Blocked correlation surface |
|---|---|---|
| Agno | tool hook | `FreshCtxAgnoBlocked.correlation` |
| LangGraph | protected action node | `FreshnessBlocked.correlation` |
| OpenAI Agents SDK | tool input guardrail | `output_info["correlation"]` |
| Google ADK | `before_tool_callback` | response `correlation` |
| ElevenLabs | `ClientTools` handler | response `correlation` |
| MCP | server `tools/call` extension | `_meta["com.freshctx/correlation"]` |

Allowed calls keep the framework's original tool result. Their correlation
record is available in the local `action_evidence_correlated` audit event.

## Portable guarantees

For equivalent current, stale, unavailable, and unrelated-change scenarios,
the conformance suite verifies that every integration records:

- one unique FreshCtx correlation ID;
- the runtime and protected action;
- the optional framework execution or request ID when available;
- the declared dependencies and reachable reasoning and observation IDs;
- unresolved dependency IDs;
- the FreshCtx state, policy decision, and allowed or blocked outcome.

The record contains no tool arguments, credentials, source contents, or
business payloads. `CURRENT` continues to mean only that declared evidence was
successfully revalidated under its adapter; it does not mean that the evidence
was the correct source to choose.

## MCP identifier separation

MCP blocked results expose two different identifiers:

- `correlationId` is the FreshCtx action/evidence correlation ID.
- `executionId` is the MCP request ID when the host supplies one.

This prevents a transport request identifier from being mistaken for the
portable FreshCtx record identifier.

## Verification

The installed-framework matrix is implemented in
`tests/test_framework_conformance.py`. It exercises the real integration
boundaries and verifies that blocked calls cannot reach the tool body.
