# Changelog

All notable FreshCtx changes will be documented here.

## Unreleased

### Added

- Versioned action/evidence correlation records for every protected synchronous
  and asynchronous action boundary, covering allowed and blocked outcomes
- Portable links across audit runs, optional framework execution IDs, actions,
  declared dependencies, reachable reasoning nodes, reachable observations,
  unresolved dependencies, freshness states, and policy decisions
- Public JSON Schema and runtime access through `Guard.correlation`,
  `FreshnessBlocked.correlation`, and `PreActionBoundary.last_correlation`

### Compatibility

- Existing `CheckResult`, freshness states, adapter contracts, stores, and
  framework blocking surfaces are unchanged.
- Action arguments, credentials, source contents, and business payloads are not
  added to correlation records or integration metadata.

## 0.10.0 - 2026-09-02

### Added

- Optional ElevenLabs Python SDK client-tool registration mapped to the shared
  pre-action contract, with synchronous and asynchronous handler support
- Bounded voice-agent customer-record scenario covering current, stale, and
  unresolved-match (`UNVERIFIABLE`) outcomes through the real `ClientTools` registry

### Compatibility

- ElevenLabs remains optional and is installed only through the `elevenlabs` extra.
- The bridge protects registered Python client tools configured to wait for a
  response. Webhook endpoints can use the same FreshCtx boundary server-side;
  ElevenLabs system tools are outside this integration.

## 0.9.0 - 2026-09-02

### Added

- Opt-in FreshCtx MCP Guard for the official MCP Python SDK v2 native `tools/call` extension boundary
- Per-tool dependency declarations, a versioned blocked-response schema, native fail-closed MCP tool results, request correlation, and argument-private audit behavior
- Current, stale, and unavailable-evidence demonstrations with independent protected tools and unprotected pass-through tools
- Real in-process and out-of-process stdio server/client validation, one named-host Codex run, and Python 3.10-3.13 MCP v2 CI coverage

### Compatibility

- The MCP Guard is optional and installed only through the `mcp-guard` extra.
- Existing MCP safe-reader behavior is unchanged. The safe-reader validates read-only evidence; the new guard controls consequential MCP tool execution.
- The official MCP SDK v2 integration is tested in a separate environment because current Google ADK dependencies use the MCP 1.x line.

## 0.8.0 - 2026-09-01

### Added

- Optional Google Agent Development Kit before-tool callback mapped to the experimental pre-action contract
- Native structured blocking response, ADK function-call correlation, named-tool filtering, and dynamic dependency resolution without exposing tool arguments
- Deterministic real-runner example plus current sync-tool, stale async-tool, privacy, filter, and configuration coverage
- Semantic configuration example covering raw-file invalidation, selected-field equivalence, and fail-closed invalid or incomplete configuration

### Compatibility

- Google ADK remains optional and is installed only through the `google-adk` extra.
- The callback covers tools that traverse the configured agent-level `before_tool_callback`; other tool execution surfaces remain outside this boundary.
- FreshCtx Core, adapters, stores, policies, schemas, Agno hooks, LangGraph wrappers, and OpenAI Agents SDK guardrails remain unchanged.

## 0.7.0 - 2026-09-01

### Added

- Optional OpenAI Agents SDK function-tool input guardrail mapped to the experimental pre-action contract
- Native SDK tripwire translation with structured FreshCtx result evidence and tool-call correlation
- Model-free real-runner example plus current, stale, async-tool, privacy, and configuration coverage

### Compatibility

- The SDK is optional and installed only through the `openai-agents` extra.
- The bridge covers custom function tools only; SDK hosted tools, built-in execution tools, handoffs, and `Agent.as_tool()` remain outside this tool-guardrail boundary.
- FreshCtx Core, adapters, stores, policies, schemas, Agno hooks, and LangGraph wrappers remain unchanged.

## 0.6.0 - 2026-08-31

### Added

- Experimental framework-neutral pre-action integration contract with non-sensitive action identity, sync/async continuations, audit correlation, conformance requirements, and an explicit stability boundary
- Experimental LangGraph action-node mapping with state-resolved dependencies, optional execution-ID correlation, and real synchronous and asynchronous graph coverage

### Changed

- The Agno 2.9 hooks now consume the experimental contract internally without changing their public call shapes or framework-specific blocking exception
- Optional framework integration names are loaded lazily so the framework-neutral contract can be imported without installing Agno

### Compatibility

- The contract is available only from `freshctx.integrations.pre_action` and is not exported as stable public API.
- Existing runtime, Agno hook, adapter, store, policy, schema, and synchronous-default behavior remains unchanged.

## 0.5.1 - 2026-08-31

### Fixed

- Live article validation now falls back from thin JSON-LD to normalized semantic article text, so body-only edits are detected without treating navigation changes as source movement.
- Live research results now state explicitly that `CURRENT` means an unchanged fingerprint, not proof that a claim is supported by the declared source.

### Compatibility

- The correction is limited to the opt-in live research-source example and its documentation. FreshCtx Core, adapters, policies, stores, schemas, and public integration APIs remain unchanged.

## 0.5.0 - 2026-08-31

### Added

- Controlled research-document example showing claim-level invalidation when one declared source changes, without interpreting the revised source
- Opt-in live research-source runner with registration-wall fail-closed handling, process-local access headers, Crossref metadata fingerprints, and selective-invalidation tests
- Optional Agno 2.9 tool-hook integration with synchronous and asynchronous protected-action boundaries and a model-free stale-deployment example

### Compatibility

- Agno remains an optional dependency and is installed only through the `agno` extra.
- Existing FreshCtx runtime APIs, adapters, stores, schemas, policies, and synchronous defaults are unchanged.
- The Agno hook protects application-declared external evidence; it does not replace Agno lifecycle, transaction, concurrency, or idempotency controls.

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
