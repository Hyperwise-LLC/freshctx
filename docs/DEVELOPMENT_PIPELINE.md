# FreshCtx development pipeline

Last updated: 2026-09-02
Current public release: `0.9.0`

PyPI, Git tag `v0.9.0`, and the GitHub Release were published after protected
PR #47 merged.

This is the canonical ordered development plan for FreshCtx. Completed releases
remain visible so product claims can be traced to public artifacts.

## Release rule

Publish a package only for a coherent product improvement. Every release must
use a protected pull request, supported-Python CI, reviewed package contents,
updated documentation, and a clean public-install check. Content cadence alone
does not justify a software release.

## Completed public milestones

1. **Core boundary and adapters** - observation, reasoning, selective
   invalidation, protected actions, stores, audit evidence, and six adapters.
2. **Bounded validation controls** - opt-in concurrency, total budgets, timing,
   evidence strategies, and explicit application responses.
3. **Core hardening** - async APIs, migrations, CLI diagnostics, conformance,
   validation reports, and package gates.
4. **Stripe Subscription** - read-only selected-field validation and bounded
   stale-webhook scenario.
5. **Research-source pattern** - controlled and live source mapping, registration
   wall handling, semantic article fingerprints, and Crossref metadata.
6. **Agno** - sync and async tool hooks through the real execution chain.
7. **LangGraph** - sync and async protected action-node wrappers.
8. **OpenAI Agents SDK** - custom function-tool input guardrail.
9. **Google ADK** - native `before_tool_callback` bridge in 0.8.0.
10. **Semantic configuration** - raw-file and selected-field examples with
    invalid or incomplete configuration becoming `UNVERIFIABLE`.
11. **Independent bounded evidence** - OpsWatch control-versus-behavior and
    Callum Pierce's four-source research-brief `r3` record.
12. **MCP Guard** - native MCP Python SDK v2 `tools/call` interception,
    fail-closed blocking, independent per-tool dependencies, request
    correlation, argument privacy, and in-process plus stdio validation in
    0.9.0.

## Completed - Wave 1 integration conformance

1. Agno, LangGraph, OpenAI Agents SDK, Google ADK, and MCP now run equivalent
   conformance scenarios through their real action boundaries.
2. The matrix verifies exact-once allowed execution, blocked-before-execution
   behavior for stale and unverifiable evidence, unrelated dependency isolation,
   argument privacy, normalized decisions, audit evidence, and Agno async blocking.
3. Protected CI runs the four compatible framework SDKs across Python 3.10-3.13
   and MCP separately because Google ADK requires MCP 1.x while MCP Guard requires
   MCP 2.x.
4. The shared integration-author contract remains experimental until external
   framework-user runs support stabilization.

## P0 - establish the MCP action boundary

1. **Released in 0.9.0** - official MCP Python SDK v2 server extension as the
   first bounded MCP Guard surface.
2. **Released in 0.9.0** - native `tools/call` interception,
   blocked-before-handler execution, fail-closed unverifiable evidence, request
   correlation, argument privacy, multiple tools, and a versioned response.
3. **Released in 0.9.0** - out-of-process stdio client/server validation
   and one named-host run through Codex from a clean wheel installation.
   Additional hosts remain external adoption tests.
4. Keep authorization, identity, transactions, retries, and idempotency outside
   the FreshCtx freshness boundary.
5. Use the results to specify a deployment-neutral MCP Guard interface before
   considering a gateway, browser guard, or commercial control plane.

## P0 - external validation

1. MCP Guard 0.9.0 independent `tools/call` reproduction.
2. Google ADK 0.8.0 real workflow.
3. LangGraph real workflow.
4. Agno consequential-tool workflow.
5. Stripe test-mode Subscription drift.
6. Longer booking or renewed-approval workflow.
7. Voice-agent canonical-record workflow.

Record package version, environment, declared dependencies, decision, observed
downstream effect, result, and limitations. Keep maintainer tests separate from
independent evidence.

## P1 - feedback-driven scenarios

1. Incident communication with sentence-level dependencies.
2. Durable database action-item claim liveness.
3. Deployment worker ownership and actionability drift.
4. Longer booking and approval comparison.
5. **Implemented for the next release** - ElevenLabs client-tool boundary and
   bounded voice-agent customer-record scenario; external voice-workflow
   validation remains pending.

Start with bounded examples using existing adapters. Add runtime or adapter
surface only when repeated workflows require the same stable behavior.

## P1 - product hardening

1. Independent-result schema above JSONL evidence.
2. Benchmark matrix by adapter, graph shape, reachability, worker count, and
   budget.
3. External adapter-author kit.
4. Longer installed-framework loops.
5. Ongoing README, website, PyPI, release, and documentation consistency audits.

## Future integration candidates

The next candidates are Microsoft Agent Framework, CrewAI, and PydanticAI,
followed by specialized Hermes and Claude Agent SDK scenarios. ElevenLabs now
has a bounded Python client-tool integration awaiting external validation.
They are considerations rather than announced commitments. Each must begin with
a bounded action-boundary use case and demonstrate demand before implementation.

Framework breadth is no longer the immediate priority after the released Wave 1
bridges. MCP Guard validation, the shared conformance contract, and independent
workflow evidence come first.

## Commercial direction

Possible Hyperwise services include architecture, integration, deployment,
managed connectors, organizational controls, evidence retention, approval
routing, and support. These are future product directions, not capabilities of
the current open-source runtime or an announced hosted service.

## Explicit non-goals

FreshCtx should not become:

- a transaction, retry, lock, or idempotency engine;
- an automatic replanning or silent agent-rerun system;
- a truth, reasoning-correctness, authorization, safety, or compliance verifier;
- a general workflow engine; or
- a hosted control plane unless that product is separately built and released.
