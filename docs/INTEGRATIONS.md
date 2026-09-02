# Integration patterns

FreshCtx is testing a small framework-neutral pre-action contract before adding more framework-specific surface. The experimental contract and its conformance requirements are documented in `docs/PRE_ACTION_CONTRACT.md`. It is not part of the stable public API.

All six supported mappings run through the shared protected conformance matrix
documented in `docs/FRAMEWORK_CONFORMANCE.md`.

## ElevenLabs

Use `register_elevenlabs_client_tool()` to register a consequential client tool
through ElevenLabs' official Python SDK. Configure the matching tool in the
ElevenLabs dashboard with **Wait for response** enabled so the conversation
receives the allow or structured blocked result.

```python
from elevenlabs.conversational_ai.conversation import ClientTools
from freshctx.integrations.elevenlabs import register_elevenlabs_client_tool

client_tools = ClientTools()
register_elevenlabs_client_tool(
    client_tools,
    "confirm_booking",
    confirm_booking,
    depends_on=[customer_decision],
    store=store,
)
```

The application owns speech-to-record matching and identity resolution. Feed
only defensible matches into the reasoning dependency map; represent an
unresolved match as an unverifiable dependency so the action fails closed.
FreshCtx then revalidates the declared canonical record immediately inside the
client-tool handler, before booking, payment, or account mutation. Raw tool
parameters are not copied into FreshCtx metadata or audit records.

The bridge protects Python client tools only. Webhook tools should place the
same FreshCtx boundary inside their application endpoint. ElevenLabs system
tools do not traverse this client-tool boundary. See
`examples/elevenlabs_voice_customer_guard.py` for a credential-free run through
the real SDK registry.

## LangGraph

Use the experimental `langgraph_action_node()` or `langgraph_async_action_node()` mapping around the action node that performs the external write. Keep observation or reasoning IDs in graph state and resolve only the dependencies for that action.

```python
from freshctx.integrations.langgraph import langgraph_action_node

protected_write = langgraph_action_node(
    write_record,
    depends_on=lambda state: [state["freshctx_decision"]],
    store=store,
    action_name="write_record",
    execution_id=lambda state: state.get("run_id"),
)
```

The bridge uses the same experimental pre-action contract as Agno. A blocking result propagates as `FreshnessBlocked` before the node body starts. LangGraph continues to own graph routing, checkpointing, interrupts, retries, and state reconciliation. See `examples/langgraph_stale_config.py` for a real installed graph with both blocked and permitted paths.

## Agno

Use `agno_tool_hook()` for synchronous Agno tools and `agno_async_tool_hook()` for asynchronous tools. Each hook wraps Agno's actual tool continuation with a FreshCtx protected-action boundary. Attach a hook to the specific tool whose declared dependencies it protects, or use it at agent level only when the same dependency set genuinely applies to every tool.

```python
from freshctx.integrations.agno import agno_tool_hook

hook = agno_tool_hook(depends_on=[decision], store=store)

@tool(tool_hooks=[hook])
def write_record(record_id: str) -> str:
    return record_id
```

The application must preserve the FreshCtx store and dependency identifiers from observation through tool execution. A stale or unverifiable dependency blocks before Agno invokes the tool body under the default policy. Internally, the Agno bridge is the first consumer of the experimental pre-action contract; its existing public hook functions and exception remain unchanged. FreshCtx does not repair Agno's internal lifecycle state, prevent concurrent invocation by itself, or replace transactions and idempotency. See `examples/agno_stale_tool.py` for a model-free test using Agno's real tool execution chain.

## OpenAI Agents SDK

Use `openai_agents_tool_guardrail()` as an input guardrail on a custom SDK function tool. The SDK supplies the actual tool name and tool-call ID; FreshCtx validates the declared dependencies immediately before the SDK invokes the tool body.

```python
from agents import function_tool
from freshctx.integrations.openai_agents import openai_agents_tool_guardrail

freshness = openai_agents_tool_guardrail(depends_on=[decision], store=store)

@function_tool(tool_input_guardrails=[freshness])
async def write_record(record_id: str) -> str:
    """Write one record."""
    return record_id
```

Under the default block policy, stale or unverifiable evidence becomes the SDK's native `ToolInputGuardrailTripwireTriggered`, and the function-tool body does not start. The exception's `output.output_info["freshctx"]` contains the FreshCtx check result. Raw tool arguments are not copied into FreshCtx metadata or audit evidence.

This bridge covers custom `function_tool` calls only. The Agents SDK does not apply tool guardrails to hosted tools, built-in execution tools, handoffs, or `Agent.as_tool()`. FreshCtx does not own model selection, tool selection, approvals, retries, handoffs, transactions, or idempotency. See `examples/openai_agents_stale_tool.py` for a model-free run through the real SDK function-tool pipeline.

## Google Agent Development Kit

Use `google_adk_tool_callback()` as an ADK agent's `before_tool_callback`. The callback uses ADK's native override behavior: `None` permits normal tool execution, while a structured dictionary skips the tool body and becomes the tool response.

```python
from freshctx.integrations.google_adk import google_adk_tool_callback

freshness = google_adk_tool_callback(
    depends_on=[decision],
    store=store,
    tool_names=["write_record"],
)

agent = Agent(
    name="bounded_agent",
    model=model,
    tools=[write_record],
    before_tool_callback=freshness,
)
```

`depends_on` may also be a resolver receiving `(tool, tool_context)` so applications can resolve FreshCtx identifiers from ADK session state without exposing tool arguments. `tool_names` limits the callback to explicitly protected tools. Both synchronous and asynchronous function tools use the same asynchronous pre-tool callback. A blocking response contains the FreshCtx result and experimental contract identifier; current evidence returns no override. The ADK function-call ID is used for audit correlation when available.

FreshCtx does not own ADK model or tool selection, sessions, state, retries, confirmations, long-running operation completion, transactions, or idempotency. Tools that do not traverse the configured agent-level before-tool callback are outside this boundary. See `examples/google_adk_stale_tool.py` for a deterministic run through ADK's real in-memory runner without an external model call.

## MCP

Use only resources or tools that are safe, read-only validators. Non-idempotent MCP operations are deliberately `UNVERIFIABLE`. Recreate readers after a process restart. Do not label an operation thread-safe unless its client and transport support concurrent calls.

### MCP tool guard

FreshCtx also provides an opt-in server extension for the official MCP Python SDK v2. It intercepts the SDK's native `tools/call` boundary immediately before the real tool handler. Current evidence proceeds to the handler; stale or unverifiable evidence returns a native MCP tool error without starting the handler.

```python
from mcp.server.mcpserver import MCPServer
from freshctx.integrations.mcp_guard import FreshCtxMCPGuard

server = MCPServer(
    "payments",
    extensions=[
        FreshCtxMCPGuard(
            depends_on={"transfer_money": [approval]},
            store=store,
            protected_tools=["transfer_money"],
        )
    ],
)
```

This integration is available in FreshCtx 0.9.0. Install it from PyPI with `python -m pip install 'freshctx[mcp-guard]==0.9.0'`. The dependency resolver receives only the MCP tool name. Tool arguments remain in the MCP SDK and are not copied into FreshCtx metadata. Authentication, authorization, transactions, retries, idempotency, and the correctness of the declared dependency map remain application responsibilities.

See `docs/MCP_GUARD.md` for the blocked-response contract, multiple-tool configuration, and scope. `examples/mcp_balance_guard.py` covers current, stale, and unverifiable evidence in process. `examples/mcp_guard_external_host.py` repeats those outcomes across a real stdio subprocess boundary.

## Postgres

Observe a narrow, deterministic, read-only query. Specify whether row order is meaningful and set a bounded statement timeout. Credentials stay in process memory and are not stored in tokens or audit events.

## Stripe Subscription

Treat webhook state as notification input, not permanent proof that a Subscription is current. Observe the authoritative Subscription with `adapter="stripe_subscription"`, select only fields that materially affect the decision, and revalidate immediately before access, entitlement, invoicing, or another consequential action. The adapter is read-only and fail-closed. It does not reconcile webhook delivery, retry payments, or replace Stripe idempotency. See `examples/stripe_subscription_drift.py`.

## Voice agents

Validate speech understanding separately from source freshness. Convert the spoken request into a canonical business record, declare the live records used by the decision, and revalidate those records immediately before booking, payment, or account mutation. See `examples/voice_agent_live_record.py`.

## Research documents

Represent each named source as an observation and each claim or section as reasoning that declares only the sources it uses. A changed source invalidates dependent claims without automatically invalidating unrelated claims. FreshCtx establishes that the source moved or could not be verified; it does not decide whether revised material still supports the claim. See `examples/document_source_drift.py` for a controlled three-source example.

For the bounded live-source pattern, treat a registration wall, HTTP 401/403, timeout, or inaccessible source as `UNVERIFIABLE`; never hash a wall page as if it were article content. Keep optional authentication headers process-local. Use structured `articleBody` when it exists. Headline and publication date alone are not a sufficient content fingerprint, so thin JSON-LD falls back to normalized visible text from the semantic article while excluding common page chrome. For DOI-backed academic claims, prefer selected Crossref metadata, including formal update, correction, and retraction relationships, over rendered publisher HTML. This avoids false invalidation from publisher layout changes. See `examples/live_document_source_validation.py`; its network access is opt-in and is not part of CI.

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

The runner never writes the cookie value to a token, audit event, or result. A wall or inaccessible source remains `UNVERIFIABLE`. `CURRENT` means only that the selected fingerprint has not changed since observation; it does not prove that a claim is supported by its declared source. Source-to-claim provenance must be reviewed separately. The bounded pass condition is that the claim states identify the same affected claim set as the researcher's same-day manual re-check; FreshCtx does not evaluate the research conclusion.

## Async services

Use `async with guard(...)` and `await ctx.run_async(...)`. FreshCtx moves synchronous adapter validation off the event-loop thread; adapter-specific timeouts and the total validation budget still apply.
