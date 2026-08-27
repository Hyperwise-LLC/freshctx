# FreshCtx™ Specification v0.1

Status: frozen release-candidate contract.

FreshCtx prevents an AI agent from reasoning or acting on stale reality. An implementation records source observations, connects reasoning to those observations, revalidates sources at a protected boundary, invalidates only transitive dependents, and emits local audit events.

## Normative objects

- `ObservationToken`: adapter, locator, fingerprint, validator version, observation time, and non-secret metadata.
- `ReasoningNode`: a derived claim with declared dependency identifiers and a deterministic digest.
- `DependencyEdge`: the directed `source_id -> dependent_id` relationship.
- `FreshnessStatus`: `CURRENT`, `STALE_SOURCE`, `STALE_REASONING`, or `UNVERIFIABLE`.

## Required behavior

Adapters return `equivalent`, `changed`, or `indeterminate`. Changed observations become `STALE_SOURCE`; reasoning nodes with a stale transitive dependency become `STALE_REASONING`; missing validators, failures, cycles, and missing dependencies become `UNVERIFIABLE`. Unrelated nodes remain `CURRENT`.

A protected-action gate MUST validate before invoking the action. The default blocking policy MUST deny `STALE_SOURCE`, `STALE_REASONING`, and `UNVERIFIABLE`. Required audit-sink failure MUST fail closed. Audit data MUST be local by default and redact common credentials.

## v0.1 adapters

Filesystem, Git, HTTP, Postgres, and MCP. Implementations remain model- and framework-neutral, local-first, account-free, and telemetry-free.

## Out of scope

Guardian, Comply, hosted control planes, enterprise administration, and benchmark branding are separate from the FreshCtx core.
