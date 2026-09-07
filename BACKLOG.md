# FreshCtx backlog

Current public release: `0.15.0`

This file is the concise issue-oriented backlog. The ordered roadmap, release
rules, completed milestones, and evidence priorities are maintained in
`docs/DEVELOPMENT_PIPELINE.md`.

## Completed - Wave 1 integration conformance

Agno, LangGraph, OpenAI Agents SDK, Google ADK, ElevenLabs, and MCP now run the
shared pre-action conformance requirements. The integration-author API remains
experimental pending external framework-user validation.

## P0 - independent evidence

1. Run Google ADK with an external ADK user.
2. Run the released LangGraph boundary in a real external graph workflow.
3. Run the Stripe Subscription adapter against a safe test-mode scenario.
4. Run longer booking, approval, and voice-agent workflows with external users.

## P1 - feedback-driven scenarios

1. Add incident communication with sentence-level dependencies.
2. Add durable database action-item claim liveness.
3. Add deployment worker ownership drift.
4. Expand the booking workflow comparison.
5. Expand voice-agent canonical-record validation.

## P1 - hardening

1. Define a machine-readable independent-result schema above the JSONL trail.
2. Expand benchmarks by adapter type, graph shape, source reachability, worker
    count, and validation budget.
3. Strengthen the external adapter-author kit and conformance suite.
4. Add longer installed-framework loops while preserving explicit action
    boundaries.

## Future integration candidates

These are considerations, not announced commitments:

- Microsoft Agent Framework
- CrewAI
- PydanticAI
- Hermes
- Claude Agent SDK

New framework work should reuse the pre-action contract where it fits and begin
with a bounded, independently testable action scenario.

## Release gate

- Protected pull request and reviewed diff
- CI across Python 3.10-3.13
- Static analysis and dependency audit
- Wheel and source distribution validation
- Clean installation of the public artifact
- README, changelog, examples, and version metadata aligned
- No unrelated pending work included
