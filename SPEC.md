# FreshCtx™ Specification v0.1

Status: frozen release-candidate contract.

FreshCtx is a runtime freshness guard that revalidates declared evidence and invalidates affected reasoning before an AI-supported action executes.

## Normative objects

- `ObservationToken`: adapter, locator, fingerprint, validator version, observation time, and non-secret metadata.
- `ReasoningNode`: a derived claim with declared dependency identifiers and a deterministic digest.
- `CheckResult`: the evaluated state, causes, adapter evidence, and policy decision.
- `FreshnessStatus`: `CURRENT`, `STALE_SOURCE`, `STALE_REASONING`, or `UNVERIFIABLE`.

## Required behavior

`ReasoningNode.dependencies` is the only normative edge representation. Implementations MUST sort and deduplicate dependency IDs. Its digest is SHA-256 over canonical JSON containing domain `freshctx.reasoning-digest.v1`, reasoning kind, normalized dependencies, and redacted metadata. Metadata keys are strings; object keys and sets are sorted, sets are stored as sorted lists, list order is preserved, and unsupported or non-finite values are rejected. The digest identifies these declared inputs. It is not a signature, authorization decision, tamper-proof record, proof of logical correctness, or substitute for adapter revalidation.

Adapters return `equivalent`, `changed`, or `indeterminate`. A changed observation is `STALE_SOURCE`; a reasoning node with any stale transitive dependency is `STALE_REASONING`; adapter indeterminacy, missing validators, failures, cycles, missing dependencies, and exceeded bounds are `UNVERIFIABLE`. Unrelated nodes remain `CURRENT`. `CURRENT` means only that all reachable declared dependencies were revalidated as equivalent under configured adapters at check time.

Persistent object IDs are immutable. A new write succeeds, an identical repeat is idempotent, and a conflicting write MUST fail without replacing the original.

A protected-action gate MUST validate before invoking the action. The default blocking policy MUST deny `STALE_SOURCE`, `STALE_REASONING`, and `UNVERIFIABLE`. Required audit-sink failure MUST fail closed. Audit data MUST be local by default and redact common credentials.

## v0.1 adapters

Filesystem, Git, HTTP, Postgres, and MCP. Postgres observes query results; it is not a FreshCtx store. MCP is an application-provided safe-reader callback contract, not a transport or complete client. External-adapter runtime state must be reconstructed after restart or validation is indeterminate. Implementations remain model- and framework-neutral, local-first, account-free, and telemetry-free.

## Out of scope

General memory, context capture, session restoration, model portability, vector storage, authorization, compliance guarantees, hosted control planes, and other Hyperwise products are outside FreshCtx v0.1.
