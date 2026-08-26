# ADR 0005: Explicit declared dependency graph

Status: accepted for v0.1

## Decision

FreshCtx tracks explicit edges from reasoning nodes to observations and other reasoning nodes. It does not infer all dependencies from prompts, traces, or model internals.

## Rationale

Explicit dependencies are deterministic, inspectable, framework-neutral, and compatible with local-first operation.

## Consequences

FreshCtx guarantees only declared dependencies. Missing edges can create false confidence, so developer tooling should make dependency declaration easy and audits should expose causal paths.
