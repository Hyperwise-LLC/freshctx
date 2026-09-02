# FreshCtx MCP Guard

Status: planned for FreshCtx 0.9.0

FreshCtx MCP Guard is an opt-in server extension for the official MCP Python
SDK v2. It intercepts a protected `tools/call` immediately before the real tool
handler. The application declares which FreshCtx evidence each consequential
tool depends on.

## Execution behavior

| Evidence result | MCP behavior | Tool handler |
|---|---|---|
| `CURRENT` | Normal MCP result | Executes once |
| `STALE_SOURCE` or `STALE_REASONING` | Structured MCP tool error | Does not start |
| `UNVERIFIABLE` | Structured MCP tool error | Does not start |

Tools outside `protected_tools` pass through without FreshCtx validation. Two
protected tools may declare different dependencies; a stale dependency for one
tool does not block an unrelated protected tool whose evidence remains current.

## Blocked-response contract

The model-visible structured result uses the stable identifier
`freshctx.mcp_guard.result.v1`:

```json
{
  "schemaVersion": "freshctx.mcp_guard.result.v1",
  "status": "blocked",
  "reason": "freshctx_pre_action_blocked",
  "tool": "transfer_money",
  "state": "STALE_REASONING",
  "policyDecision": "block",
  "correlationId": "117"
}
```

The corresponding JSON Schema is packaged as
`freshctx/schemas/mcp-guard-result.schema.json`. The response deliberately
excludes dependency values, tool arguments, credentials, and raw business
payloads. The MCP result `_meta` contains the complete redacted FreshCtx result
for the client application and the pre-action contract identifier.

`correlationId` is the MCP request ID when the server provides one. It may be
`null` on an execution surface without a request ID.

## Installation and configuration

Before the 0.9.0 package is published, install the branch from source:

```bash
python -m pip install -e '.[mcp-guard]'
```

After release, the command becomes:

```bash
python -m pip install 'freshctx[mcp-guard]==0.9.0'
```

Attach the guard when constructing the MCP server:

```python
from mcp.server.mcpserver import MCPServer
from freshctx.integrations.mcp_guard import FreshCtxMCPGuard

server = MCPServer(
    "payments",
    extensions=[
        FreshCtxMCPGuard(
            depends_on={
                "transfer_money": [transfer_approval],
                "approve_refund": [refund_approval],
            },
            protected_tools=["transfer_money", "approve_refund"],
            store=store,
        )
    ],
)
```

The dependency resolver receives only the tool name. It never receives the MCP
arguments.

## Verification examples

- `examples/mcp_balance_guard.py` runs all three outcomes in process.
- `examples/mcp_guard_external_host.py` launches the MCP server as a separate
  stdio process, discovers four tools, calls them through an external client,
  and reads the execution log after each protected call.
- `docs/MCP_HOST_VALIDATION.md` records a named-host run through Codex using a
  clean installation of the 0.9.0 release candidate.
- `tests/test_mcp_guard_integration.py` proves handler execution counts,
  independent per-tool dependencies, response conformance, request correlation,
  and argument privacy.

The stdio test is a real transport and process boundary, and the Codex run is
one named-host validation. Neither is evidence of compatibility with every MCP
host, transport, or deployment.

## Product boundary

MCP authentication and authorization answer whether a caller may invoke a tool.
FreshCtx answers whether the evidence that justified this particular action is
still current. FreshCtx does not replace identity, authorization, transaction
isolation, retries, idempotency, tool correctness, or downstream outcome checks.
