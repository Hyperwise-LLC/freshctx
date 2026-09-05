# FreshCtx project status

Last updated: 2026-09-02
Current public release: `0.12.0`
Current release candidate: `0.13.0`

PyPI, Git tag `v0.12.0`, and the GitHub Release were published on 2026-09-05
after protected PR #59 merged.

## Current milestone

FreshCtx 0.10.0 preserves the original synchronous
Core contract while adding opt-in concurrency, async protected actions,
validation budgets, stronger developer tooling, six adapters, and native
pre-action mappings for Agno, LangGraph, the OpenAI Agents SDK, Google ADK, and
the official MCP Python SDK v2, plus an ElevenLabs Python client-tool bridge.

The 0.9.0 package adds an MCP server extension
at the native `tools/call` boundary, a versioned blocked-response schema,
independent per-tool dependencies, three-outcome demonstrations, and a real
out-of-process stdio validation. A named-host run through Codex also returned
the expected FreshCtx stale-evidence block.

The 0.10.0 package adds an optional ElevenLabs client-tool integration and a
bounded customer-record scenario. Matching current evidence permits exactly
one consequential action; changed canonical evidence or an unresolved
speech-to-record match blocks before the handler runs. Semantic matching and
identity resolution remain application-owned. A live external voice-workflow
run remains an adoption test, not a release claim.

## Released runtime

- `ObservationToken`, `ReasoningNode`, `CheckResult`, and four freshness states
- selective, transitive dependency invalidation
- synchronous and asynchronous guards and protected actions
- default blocking plus `warn`, `allow`, `replan`, and `require_approval` responses
- bounded concurrent validation, adapter timeouts, and total validation budgets
- SQLite and in-memory stores with schema migration and integrity diagnostics
- local JSONL audit events, timing evidence, validation reports, and redaction
- `freshctx demo`, `freshctx check`, `freshctx audit`, and `freshctx doctor`

## Released adapters

- Filesystem
- Git
- HTTP
- Postgres
- Stripe Subscription
- MCP safe reader

Adapters own their equivalence rules and return indeterminate results when a
source cannot be checked safely. Unknown conditions never silently become
`CURRENT`.

## Released framework mappings

- Agno 2.9 tool hooks
- LangGraph synchronous and asynchronous action-node wrappers
- OpenAI Agents SDK custom function-tool input guardrail
- Google ADK `before_tool_callback`
- MCP Python SDK v2 native `tools/call` extension
- ElevenLabs Python SDK client-tool registration

All six mappings consume the same experimental pre-action contract. A shared
conformance suite now exercises equivalent allow, stale, unverifiable, and
unrelated-change scenarios through the real framework boundaries. The
framework-specific bridges are released; the shared integration-author
contract remains experimental while external framework-user validation
continues.

## Public evidence

- CI covers Python 3.10-3.13, package construction, static analysis, dependency
  checks, Windows onboarding, and installed-package smoke tests.
- The OpsWatch JSONL experiment separates a FreshCtx control decision from the
  downstream agent's observed behavior.
- The independent research-brief `r3` record documents four claims mapped to
  four named sources after an unsupported claim remained excluded until a
  defensible receipt was supplied.

These are bounded results, not claims of production, regulatory, scientific,
or general workflow validation.

## Current priorities

1. Obtain independent Google ADK, LangGraph, Agno, Stripe test-mode, booking,
   approval, and ElevenLabs voice-workflow runs.
2. Complete bounded incident-communication, durable action-item, deployment
   ownership, longer booking, and voice-agent scenarios.
3. Expand the independent-result schema, benchmark matrix, adapter-author kit,
   and longer framework loops.

See `docs/DEVELOPMENT_PIPELINE.md` for the ordered public plan.

## Product boundary

FreshCtx revalidates application-declared evidence. It does not verify truth,
reasoning correctness, authorization, safety, compliance, transaction outcome,
or global reality. It is not a workflow engine, memory system, retry engine, or
hosted enterprise control plane.

## Canonical documents

- `README.md` - current onboarding and capability overview
- `CHANGELOG.md` - released changes by version
- `docs/DEVELOPMENT_PIPELINE.md` - current ordered development plan
- `API.md` and `SPEC.md` - frozen v0.1 compatibility contract
- `docs/PRE_ACTION_CONTRACT.md` - experimental framework bridge contract
- `docs/FEEDBACK_VALIDATION_PLAN.md` - bounded validation scenarios
- `docs/INTEGRATIONS.md` - current framework and adapter patterns
