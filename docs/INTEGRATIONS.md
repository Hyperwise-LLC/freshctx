# Integration patterns

## LangGraph

Place `Guard.run()` or `await Guard.run_async()` in the action node immediately before the external write. Keep observation and reasoning IDs in graph state. See `examples/langgraph_stale_config.py`.

## Agno

Use `agno_tool_hook()` for synchronous Agno tools and `agno_async_tool_hook()` for asynchronous tools. Each hook wraps Agno's actual tool continuation with a FreshCtx protected-action boundary. Attach a hook to the specific tool whose declared dependencies it protects, or use it at agent level only when the same dependency set genuinely applies to every tool.

```python
from freshctx.integrations.agno import agno_tool_hook

hook = agno_tool_hook(depends_on=[decision], store=store)

@tool(tool_hooks=[hook])
def write_record(record_id: str) -> str:
    return record_id
```

The application must preserve the FreshCtx store and dependency identifiers from observation through tool execution. A stale or unverifiable dependency blocks before Agno invokes the tool body under the default policy. FreshCtx does not repair Agno's internal lifecycle state, prevent concurrent invocation by itself, or replace transactions and idempotency. See `examples/agno_stale_tool.py` for a model-free test using Agno's real tool execution chain.

## MCP

Use only resources or tools that are safe, read-only validators. Non-idempotent MCP operations are deliberately `UNVERIFIABLE`. Recreate readers after a process restart. Do not label an operation thread-safe unless its client and transport support concurrent calls.

## Postgres

Observe a narrow, deterministic, read-only query. Specify whether row order is meaningful and set a bounded statement timeout. Credentials stay in process memory and are not stored in tokens or audit events.

## Stripe Subscription

Treat webhook state as notification input, not permanent proof that a Subscription is current. Observe the authoritative Subscription with `adapter="stripe_subscription"`, select only fields that materially affect the decision, and revalidate immediately before access, entitlement, invoicing, or another consequential action. The adapter is read-only and fail-closed. It does not reconcile webhook delivery, retry payments, or replace Stripe idempotency. See `examples/stripe_subscription_drift.py`.

## Voice agents

Validate speech understanding separately from source freshness. Convert the spoken request into a canonical business record, declare the live records used by the decision, and revalidate those records immediately before booking, payment, or account mutation. See `examples/voice_agent_live_record.py`.

## Research documents

Represent each named source as an observation and each claim or section as reasoning that declares only the sources it uses. A changed source invalidates dependent claims without automatically invalidating unrelated claims. FreshCtx establishes that the source moved or could not be verified; it does not decide whether revised material still supports the claim. See `examples/document_source_drift.py` for a controlled three-source example.

For the bounded live-source pattern, treat a registration wall, HTTP 401/403, timeout, or inaccessible source as `UNVERIFIABLE`; never hash a wall page as if it were article content. Keep optional authentication headers process-local. For DOI-backed academic claims, prefer selected Crossref metadata, including formal update, correction, and retraction relationships, over rendered publisher HTML. This avoids false invalidation from publisher layout changes. See `examples/live_document_source_validation.py`; its network access is opt-in and is not part of CI.

Run the public three-source check with:

```bash
python examples/live_document_source_validation.py --output live-document-result.json
```

If the C&EN article requires an authenticated session, place the complete Cookie header in an environment variable and name that variable without putting its value on the command line:

```bash
python examples/live_document_source_validation.py \
  --cen-cookie-env CEN_SESSION_COOKIE \
  --output live-document-result.json
```

The runner never writes the cookie value to a token, audit event, or result. A wall or inaccessible source remains `UNVERIFIABLE`. The bounded pass condition is that the claim states identify the same affected claim set as the researcher's same-day manual re-check; FreshCtx does not evaluate the research conclusion.

## Async services

Use `async with guard(...)` and `await ctx.run_async(...)`. FreshCtx moves synchronous adapter validation off the event-loop thread; adapter-specific timeouts and the total validation budget still apply.
