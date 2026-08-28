# FreshCtx architecture

## System purpose

FreshCtx determines whether evidence and the reasoning derived from it remain current at the moment an AI agent produces a protected output or performs a protected action.

The core data flow is:

```text
source -> adapter.observe() -> ObservationToken
ObservationToken(s) -> reasoning() -> ReasoningNode
ReasoningNode -> guard.check() -> CheckResult
CheckResult + policy -> allow, warn, refresh, or block
all significant transitions -> AuditEvent
```

## Components

### Public API

`guard()`, `observe()`, `reasoning()`, and `Guard.run()` provide the framework-neutral Python surface. The API establishes a run-local context, records declared dependencies, and validates plus audits immediately before protected actions.

### Adapter registry

Adapters translate heterogeneous source state into versioned observation tokens. Every adapter implements:

```python
observe(locator, **options) -> ObservationToken
validate(token) -> AdapterResult
```

Validation must be read-only. An adapter returns `equivalent`, `changed`, or `indeterminate`; it never directly selects a FreshCtx policy.

### Dependency graph

Observation tokens are leaves. Reasoning nodes reference observations or other reasoning nodes. The evaluator traverses the declared subgraph, detects missing objects and cycles, validates unique observations, and propagates stale or unverifiable states toward the protected subject.

### Evaluator

Evaluation order is deterministic:

1. Resolve the protected subject.
2. Load and validate the dependency graph.
3. Deduplicate and validate source observations.
4. Propagate source outcomes through reasoning nodes.
5. Aggregate the final state.
6. Apply policy.
7. Emit the audit result before returning or raising.

State precedence is stale over unverifiable over current. A stale observation produces `STALE_SOURCE`; a reasoning node depending on stale input produces `STALE_REASONING`.

### Policy engine

The policy layer consumes a `CheckResult`. The default `block` policy fails closed. `warn` and `allow` preserve the non-current result in audit events. The implemented `refresh` policy performs at most one caller-supplied refresh and one recheck before blocking.

### Storage

The default local store is SQLite at `.freshctx/freshctx.db`, using WAL mode and atomic transactions. Tests may use `MemoryStore`. Stored objects are immutable by ID; replacement is permitted only for identical logical records during idempotent writes.

SQLite is FreshCtx persistence. The Postgres adapter only observes application query results. Conflicting writes raise `StorageConflictError` and leave the original record unchanged.

### Audit

The default sink is append-only JSONL at `.freshctx/audit.jsonl`. Events include `schema_version`, `event_id`, `run_id`, type, timestamp, subject, and redacted details. An audit failure under the blocking policy must eventually produce `UNVERIFIABLE` and prevent the protected operation.

## Trust boundaries

- FreshCtx trusts adapters to implement side-effect-free validation.
- FreshCtx does not trust source availability, credentials, source metadata, or adapter exceptions.
- Raw source content, prompts, model outputs, credentials, and authorization material are excluded by default.
- FreshCtx guarantees only declared dependencies. Undeclared evidence cannot be evaluated.
- `CURRENT` covers only reachable declared dependencies successfully revalidated under configured adapters at check time; it does not prove source truth, logical correctness, authorization, safety, compliance, or global reality.
- HTTP, Postgres, and MCP perform external calls only when explicitly selected. Their readers, credentials, and other process-local validation state must be reconstructed after restart.

### Reasoning digest

`ReasoningNode.dependencies` is the canonical edge representation. IDs are sorted and deduplicated. The v0.1 digest is SHA-256 over canonical JSON containing domain `freshctx.reasoning-digest.v1`, the reasoning kind, normalized dependencies, and redacted metadata. It is identity/integrity metadata for those fields, not a signature, correctness proof, authorization result, or freshness check.

## Concurrency model

Run-local state uses `contextvars` to prevent dependency leakage between concurrent guards. SQLite access must be safe for supported thread usage. v0.1 does not guarantee multi-host coordination or distributed consensus.

## Extension model

New adapters register a unique name, version their validator evidence, return only safe audit evidence, and satisfy the shared adapter test suite. Model or framework integrations must remain optional extras layered above the core API.

## Package layout

```text
src/freshctx/
  __init__.py   public exports
  model.py      canonical domain objects and states
  adapters.py   adapter implementations and registry
  core.py       contexts, evaluator, policies, and audit
  store.py      SQLite and memory persistence
schemas/        JSON Schema contracts
docs/           concept and technical specifications
adr/            architectural decisions
examples/       executable demonstrations
tests/          behavioral and acceptance tests
```
