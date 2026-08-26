# FreshCtx v0.1 implementation backlog

Issues are ordered for a single initial milestone. Each item should become one Git-hosting issue and reference the technical specification.

## Completed v0.1 implementation items

1. Protected action wrapper — completed
   - Validate immediately before invoking a side effect.
   - Add tests proving blocked actions never execute.
2. Graph validation — completed
   - Detect cycles and missing dependencies without recursion failure.
   - Implements acceptance test A8.
3. Audit failure behavior — completed
   - Convert write failures to `UNVERIFIABLE` under block policy.
   - Implements A11.
4. Redaction layer — completed baseline
   - Redact credentials, DSNs, headers, cookies, and configurable keys.
   - Implements A12.
5. Refresh policy — completed
   - One bounded callback cycle; rebuild and recheck; otherwise block.
   - Implements A9.

## Completed adapter contracts

6. HTTP adapter — completed
   - Conditional HEAD/GET, strong and weak ETag rules, Last-Modified, body hash, redirect limits, timeout handling.
   - Implements A3-A4.
7. Postgres adapter — completed with injected-connector tests
   - Read-only validation, statement timeout, canonical rows, ordered/unordered query semantics.
   - Implements A6.
8. MCP adapter — completed with safe-reader tests
   - Server identity, normalized arguments, safe resource/tool validator, non-idempotent protection.
   - Implements A7.

## P1 — runtime quality

9. Concurrency isolation — completed for concurrent thread guards
   - Concurrent guards, run IDs, SQLite access, context propagation.
   - Implements A10.
10. Public exception hierarchy
    - Configuration, adapter, storage, schema, and enforcement exceptions.
11. Store migrations
    - Schema version table, forward migration command, corruption handling.
12. Shared adapter conformance tests
    - Equivalent/changed/indeterminate, timeouts, redaction, side-effect safety.

## P2 — packaging and developer experience

13. CLI
    - `freshctx check`, `freshctx audit`, `freshctx doctor`, and schema version reporting.
14. Type-checking and formatting
    - Add Ruff and mypy or Pyright configuration after dependency policy is approved.
15. Package build verification
    - Build wheel and source distribution; install into a clean environment.
16. Documentation examples
    - Filesystem, Git, HTTP, Postgres, MCP, and framework-neutral agent examples.
17. Performance baseline
    - Graph traversal, hash cost, validation latency, and large-directory behavior.

## Release gate

- Acceptance tests A1-A12 pass.
- Python 3.10-3.13 CI passes.
- Wheel and source distribution install cleanly.
- No required account, telemetry, or model framework.
- License, security policy, changelog, API contract, schemas, and migration notes are present.
