# Framework integration conformance

Conformance verifies that FreshCtx enforces the same protected-action guarantee
through every released framework and protocol boundary. It is a reliability and
compatibility test, not a separate runtime feature.

## Shared guarantee

> If required evidence is stale or cannot be verified, the consequential tool
> does not execute.

The suite runs the same source fixture, dependency graph, sensitive argument,
and four situations through real Agno, LangGraph, OpenAI Agents SDK, Google ADK,
and MCP execution paths.

| Situation | Required result |
| --- | --- |
| Evidence remains unchanged | Tool executes exactly once |
| Required evidence changes | Tool does not execute |
| Required evidence cannot be checked | Tool does not execute |
| Unrelated evidence changes | Protected tool still executes exactly once |

Every result is normalized for testing as `status`, `state`, `policy_decision`,
and execution count. The suite also verifies that:

- framework blocking cannot fall through to the protected action;
- sensitive tool arguments do not appear in FreshCtx objects or JSONL audit records;
- each integration records the runtime, action, and experimental contract version;
- policy evidence records every allow/block decision, and allowed execution is
  recorded before the protected action starts;
- repeated or duplicate execution does not occur;
- an asynchronous Agno tool is blocked before execution; and
- the matrix runs under Python 3.10 through 3.13 in protected CI.

Frameworks retain their native success and blocking surfaces. Normalization is
test-only and does not replace those public framework-specific APIs.

## Run locally

Google ADK currently requires MCP 1.x, while MCP Guard requires MCP 2.x. The
same conformance contract therefore runs in two valid environments rather than
forcing incompatible SDK versions into one installation.

Run the four agent-framework mappings:

```console
python -m pip install -e '.[conformance]'
python -m unittest tests.test_framework_conformance -v
```

Run MCP Guard in a separate environment:

```console
python -m pip install -e '.[mcp-guard]'
FRESHCTX_CONFORMANCE_RUNTIMES=mcp python -m unittest tests.test_framework_conformance -v
```

## Integration points

| Runtime | Protected boundary |
| --- | --- |
| Agno | Tool hook |
| LangGraph | Action node |
| OpenAI Agents SDK | Function-tool input guardrail |
| Google ADK | `before_tool_callback` |
| MCP | Native `tools/call` extension boundary |

Conformance does not make the experimental pre-action contract stable. External
integration-user validation is still required before FreshCtx considers that
integration-author surface stable.
