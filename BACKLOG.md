# FreshCtx backlog

Current public release: `0.8.0`

This file is the concise issue-oriented backlog. The ordered roadmap, release
rules, completed milestones, and evidence priorities are maintained in
`docs/DEVELOPMENT_PIPELINE.md`.

## P0 - Wave 1 integration conformance

1. Compare Agno, LangGraph, OpenAI Agents SDK, and Google ADK against the same
   pre-action requirements.
2. Confirm that every bridge checks at the true action boundary, blocks before
   execution, preserves non-sensitive correlation, and retains application-owned
   policy decisions.
3. Decide whether the experimental pre-action contract is ready to become a
   stable integration-author API.

## P0 - independent evidence

4. Run Google ADK 0.8.0 with an external ADK user.
5. Run the released LangGraph boundary in a real external graph workflow.
6. Run the Stripe Subscription adapter against a safe test-mode scenario.
7. Run longer booking, approval, and voice-agent workflows with external users.

## P1 - feedback-driven scenarios

8. Add incident communication with sentence-level dependencies.
9. Add durable database action-item claim liveness.
10. Add deployment worker ownership drift.
11. Expand the booking workflow comparison.
12. Expand voice-agent canonical-record validation.

## P1 - hardening

13. Define a machine-readable independent-result schema above the JSONL trail.
14. Expand benchmarks by adapter type, graph shape, source reachability, worker
    count, and validation budget.
15. Strengthen the external adapter-author kit and conformance suite.
16. Add longer installed-framework loops while preserving explicit action
    boundaries.

## Future integration candidates

These are considerations, not announced commitments:

- Microsoft Agent Framework
- CrewAI
- PydanticAI
- ElevenLabs
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
