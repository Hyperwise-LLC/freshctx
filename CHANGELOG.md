# Changelog

All notable FreshCtx changes will be documented here.

## 0.4.0 - 2026-08-30

### Added

- Read-only Stripe Subscription adapter with selected-field fingerprints, process-local credentials, bounded HTTP validation, and fail-closed error handling
- Bounded stale-webhook versus authoritative-subscription example and adapter regression coverage

### Compatibility

- Stripe validation is additive and runs only when `adapter="stripe_subscription"` is explicitly selected.
- Existing adapters, synchronous defaults, policies, stores, schemas, and audit events are unchanged.

## 0.3.0 - 2026-08-30

### Added

- Forward-only SQLite schema versioning, legacy-store migration, and integrity diagnostics
- Native async guard, check, and protected-action entry points
- `freshctx check`, `freshctx audit`, and `freshctx doctor` commands
- Portable bounded-validation report schema
- Shared adapter contract validation and fail-closed invalid-result handling
- Large-graph, migration, async, CLI, and v0.1 compatibility coverage
- Enforced static-analysis, package, and release-quality gates

### Compatibility

- Existing synchronous calls and default single-worker behavior remain unchanged.
- Existing v0.1 SQLite object tables migrate in place without rewriting stored objects.

## 0.2.1 - 2026-08-30

### Fixed

- Mark the synthetic benchmark adapter as thread-safe so requested worker concurrency is actually measured.
- Add a release test preventing the benchmark from silently reverting to sequential validation.

## 0.2.0 - 2026-08-30

### Added

- Opt-in bounded concurrent validation with synchronous v0.1 behavior retained by default
- Total validation budgets that fail closed as `UNVERIFIABLE`
- Per-adapter and total-check timing evidence
- Exact, version, fingerprint, TTL, attestation, and deliberately unverifiable evidence strategies
- Application-owned `replan` and `require_approval` responses without adding freshness states
- Standalone installed-package demo requiring no repository clone
- Sequential/concurrent benchmark harness
- Booking renewed-approval and live voice-agent examples
- Feedback-driven compatibility and performance tests
- Capability-gated concurrency; custom and MCP adapters remain sequential unless safety is explicit
- Validator cleanup guarantees so no started validation survives beyond `check()`

### Compatibility

- Existing API calls retain their v0.1 defaults.
- Audit events remain schema version 1; existing fields and event names are unchanged.
- `FreshnessBlocked` remains the enforcement exception for every blocking response.
- Validation budgets are decision-validity budgets, not unsafe hard thread cancellation.

## 0.1.1 - 2026-08-29

### Added

- A minimal LangGraph action-node integration demonstrating stale configuration blocking
- A `langgraph` optional dependency and release-gate coverage for the integration

### Changed

- PyPI installation is now the primary README onboarding path
- Package discovery metadata and release verification documentation were improved

## 0.1.0 - 2026-08-27

### Added

- Core observation and reasoning data models
- Filesystem adapter
- Git repository- and path-scoped adapter
- Transitive freshness evaluation
- Blocking, warning, and allow policies
- SQLite and in-memory stores
- Local JSONL audit events
- Initial end-to-end tests
- Pre-action protected execution
- Graph corruption and depth safeguards
- Fail-closed audit handling and redaction
- HTTP, Postgres, and MCP adapter contracts
- Bounded refresh and concurrency isolation
- Wheel packaging and release automation
- External developer gate coverage for selective invalidation and safe connection-loss behavior
- Three executable reference demos for file, configuration/API, and audit reasoning drift
- Versioned deterministic reasoning digests over normalized dependencies and redacted metadata
- Immutable-by-ID SQLite and memory-store writes with conflict errors
- Runtime-produced JSON Schema conformance and negative-fixture coverage
- Bounded streaming filesystem traversal with explicit symlink and root policy
- Community security, conduct, support, ownership, trademark, and third-party notices
