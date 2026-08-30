# FreshCtx project status

## Current milestone

Feedback-driven v0.2 development. PyPI v0.2.0 is public; v0.2.1 corrects the synthetic benchmark's concurrency declaration before external test invitations.

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
- MCP safe-reader and non-idempotent operation contract
- Packaging and tag-triggered release automation
- Private-phase workflow is build-only; public package publishing is disabled

## Validated for the private v0.1 candidate

- Python 3.10-3.13 compatibility matrix
- Windows PowerShell and Command Prompt virtual-environment activation on a real Windows CI runner
- Disposable real-service Postgres validation and connection-loss behavior
- HTTP and MCP connection-loss behavior
- Clean wheel and source-distribution installation
- Dependency, secret, license, and package-content scans
- External developer workflow using only the README

The v0.2 branch adds opt-in bounded adapter concurrency without changing the synchronous guard contract. Native async contexts and independent third-party security review remain future hardening work.

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
