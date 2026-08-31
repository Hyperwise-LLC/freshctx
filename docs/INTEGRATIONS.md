# Integration patterns

## LangGraph

Place `Guard.run()` or `await Guard.run_async()` in the action node immediately before the external write. Keep observation and reasoning IDs in graph state. See `examples/langgraph_stale_config.py`.

## MCP

Use only resources or tools that are safe, read-only validators. Non-idempotent MCP operations are deliberately `UNVERIFIABLE`. Recreate readers after a process restart. Do not label an operation thread-safe unless its client and transport support concurrent calls.

## Postgres

Observe a narrow, deterministic, read-only query. Specify whether row order is meaningful and set a bounded statement timeout. Credentials stay in process memory and are not stored in tokens or audit events.

## Stripe Subscription

Treat webhook state as notification input, not permanent proof that a Subscription is current. Observe the authoritative Subscription with `adapter="stripe_subscription"`, select only fields that materially affect the decision, and revalidate immediately before access, entitlement, invoicing, or another consequential action. The adapter is read-only and fail-closed. It does not reconcile webhook delivery, retry payments, or replace Stripe idempotency. See `examples/stripe_subscription_drift.py`.

## Voice agents

Validate speech understanding separately from source freshness. Convert the spoken request into a canonical business record, declare the live records used by the decision, and revalidate those records immediately before booking, payment, or account mutation. See `examples/voice_agent_live_record.py`.

## Async services

Use `async with guard(...)` and `await ctx.run_async(...)`. FreshCtx moves synchronous adapter validation off the event-loop thread; adapter-specific timeouts and the total validation budget still apply.
