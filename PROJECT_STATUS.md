# FreshCtx project status

## Current milestone

Pre-release v0.1 implementation.

## Implemented

- `ObservationToken`, `ReasoningNode`, `CheckResult`, and freshness states
- Filesystem source observation and validation
- Git repository- and path-scoped observation and validation
- Transitive stale-reasoning propagation
- Default blocking policy plus warning and allow policies
- SQLite and in-memory stores
- Local JSONL audit trail
- Context-isolated guard API
- Eighteen passing unit, contract, concurrency, and acceptance tests
- Protected pre-action execution through `Guard.run()`
- Cycle, missing-dependency, and maximum-depth graph validation
- Fail-closed audit behavior under blocking policies
- Default secret redaction
- HTTP conditional validation and timeout handling
- Bounded refresh callback behavior
- Concurrent guard isolation tests
- Postgres canonical query-result adapter contract
- MCP safe-reader and non-idempotent operation contract
- Packaging and tag-triggered release automation
- Private-phase workflow is build-only; public package publishing is disabled

## Required before v0.1 release

- Python 3.10-3.13 compatibility matrix
- Real-service integration suites for Postgres and MCP
- External security review and adversarial adapter testing
- Async guard behavior and public API stabilization

## Canonical documents

- `docs/FreshCtx_One_Page_Brief.docx`
- `docs/FreshCtx_v0.1_Technical_Specification.docx`

The technical specification is authoritative when implementation details conflict with summaries or examples.

## Developer handoff contracts

- `ARCHITECTURE.md` defines components, trust boundaries, data flow, and extension rules.
- `API.md` defines the provisional public Python contract and known API work.
- `schemas/` defines machine-readable domain and audit structures.
- `adr/` records accepted architectural decisions.
- `BACKLOG.md` is the issue-ready v0.1 implementation plan.
- `.github/workflows/ci.yml` tests Python 3.10-3.13 and builds distributions.
