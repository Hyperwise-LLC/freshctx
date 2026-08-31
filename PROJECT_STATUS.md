# FreshCtx project status

## Current milestone

FreshCtx Core 0.4.0 adds a read-only Stripe Subscription adapter and bounded stale-webhook scenario while retaining the v0.1 synchronous compatibility defaults. Local release gates and clean wheel installation pass; public PyPI verification remains pending until the protected 0.4.0 release completes.

## Implemented

- `ObservationToken`, `ReasoningNode`, `CheckResult`, and freshness states
- Filesystem source observation and validation
- Git repository- and path-scoped observation and validation
- Transitive stale-reasoning propagation
- Default blocking policy plus warning and allow policies
- SQLite and in-memory stores
- Local JSONL audit trail
- Context-isolated guard API
- Complete unit, contract, concurrency, schema, and acceptance test suite
- Protected pre-action execution through `Guard.run()`
- Cycle, missing-dependency, and maximum-depth graph validation
- Fail-closed audit behavior under blocking policies
- Default secret redaction
- HTTP conditional validation and timeout handling
- Bounded refresh callback behavior
- Concurrent guard isolation tests
- Postgres canonical query-result adapter contract
- Read-only Stripe Subscription selected-field adapter with process-local credentials
- MCP safe-reader and non-idempotent operation contract
- Packaging and tag-triggered release automation
- Public releases use protected pull requests, passing CI, and a separate explicitly authorized PyPI publication step

## Validated for the private v0.1 candidate

- Python 3.10-3.13 compatibility matrix
- Windows PowerShell and Command Prompt virtual-environment activation on a real Windows CI runner
- Disposable real-service Postgres validation and connection-loss behavior
- HTTP and MCP connection-loss behavior
- Clean wheel and source-distribution installation
- Dependency, secret, license, and package-content scans
- External developer workflow using only the README

The current development branch adds native async entry points without changing the synchronous guard contract. Independent third-party validation remains evidence work and must stay distinct from maintainer verification.

## Canonical documents

- `docs/FreshCtx_One_Page_Brief.docx`
- `docs/FreshCtx_v0.1_Technical_Specification.docx`

The technical specification is authoritative when implementation details conflict with summaries or examples.

## Developer handoff contracts

- `ARCHITECTURE.md` defines components, trust boundaries, data flow, and extension rules.
- `API.md` defines the frozen v0.1 Python contract.
- `schemas/` defines machine-readable domain and audit structures.
- `adr/` records accepted architectural decisions.
- `BACKLOG.md` is the issue-ready v0.1 implementation plan.
- `.github/workflows/ci.yml` tests Python 3.10-3.13, executes Windows onboarding commands, and builds distributions.
