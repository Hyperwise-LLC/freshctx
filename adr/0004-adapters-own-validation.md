# ADR 0004: Adapters own side-effect-free validation

Status: accepted for v0.1

## Decision

Adapters own source-specific observation evidence and validation. The core evaluator consumes only `equivalent`, `changed`, or `indeterminate` outcomes.

## Rationale

Freshness semantics differ across files, Git, HTTP, databases, and MCP. Keeping them behind one contract permits heterogeneous instrumentation without centralizing application state.

## Consequences

Adapters must version their validator evidence, avoid side effects, redact secrets, and pass a shared conformance suite. Non-idempotent operations require separate safe validators or produce `UNVERIFIABLE`.
