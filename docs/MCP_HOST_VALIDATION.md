# MCP named-host validation

Date: 2026-09-01

Release candidate: FreshCtx 0.9.0

Host: OpenAI Codex CLI `0.151.0-alpha.7.2`

Transport: local stdio MCP server loaded from a clean installation of the
FreshCtx 0.9.0 wheel with the `mcp-guard` extra.

## Scenario

The host invoked the protected `transfer_money` tool once with a balance
dependency that had changed after the reasoning record was created.

## Observed result

The native MCP tool call returned an error result containing:

```text
FreshCtx blocked transfer_money: declared evidence is STALE_REASONING.
```

The protected handler did not proceed. The same release candidate also verifies
handler non-execution through the automated stdio execution-log test.

## Scope

This is one named-host validation, not a claim that every MCP host, transport,
or SDK version has been tested. Automated CI separately covers the official MCP
Python SDK v2 across Python 3.10 through 3.13, the three FreshCtx outcomes, and
multiple protected tools with independent dependency sets.
