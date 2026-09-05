# Agent-driven provenance and enforcement

FreshCtx can place two independent checks before a consequential action:

1. Revalidate the declared evidence and retain the normal FreshCtx freshness
   result.
2. Evaluate whether successful observed reads satisfy an application-declared
   provenance policy.

The protected action runs only after both checks allow it.

```python
capture = ObservedReadCapture("records")
record = capture.read_text("customer-42.json")

# The application observes and reasons from the selected source.

provenance = ProvenanceBoundary(capture)
with guard(store=store) as ctx:
    provenance.invoke(
        ctx,
        update_account,
        depends_on=[decision],
        selected_source="customer-42.json",
        cited_sources=("customer-42.json",),
        required_sources=("customer-42.json",),
    )
```

## Enforcement outcomes

| Freshness | Provenance | Default action outcome |
| --- | --- | --- |
| `CURRENT` | `CONSISTENT` | Allowed |
| `CURRENT` | `INCONSISTENT` | Blocked |
| `CURRENT` | `NOT_ASSESSED` | Blocked |
| Stale or unverifiable | Not reached | Blocked by FreshCtx |

Applications may explicitly allow `NOT_ASSESSED` with
`ProvenanceBoundary(capture, on_not_assessed="allow")`. `INCONSISTENT` always
blocks at this boundary.

`ProvenanceBlocked` exposes both the observed evidence receipt and the
versioned `freshctx.provenance_enforcement.v1` decision. The enforcement record
links to the same action/evidence correlation while retaining the original
freshness state unchanged.

## Agent-driven demonstration

The packaged example uses the real OpenAI Agents SDK tool loop. Its repeatable
mode uses the SDK's `ScriptedModel`, so CI and external developers can reproduce
the exact tool sequence without credentials:

```console
python examples/agent_source_provenance.py
```

It covers:

- authoritative source read, selected, and cited: action allowed;
- decoy read and selected: freshness remains `CURRENT`, provenance blocks;
- authoritative source read but uninspected decoy cited: provenance blocks.

For a live model-selected run:

```console
OPENAI_API_KEY=... python examples/agent_source_provenance.py --live
```

The agent can obtain file contents only through the instrumented `read_source`
tool. The receipt is therefore generated from tool-backed file access rather
than an agent's statement about what it inspected.

## Boundaries

- Required-source policy and semantic correctness remain application-owned.
- FreshCtx does not infer whether a document is truthful or authoritative.
- The hook cannot observe reads performed through an uninstrumented path.
- Source contents, credentials, action arguments, and model prompts are not
  copied into provenance receipts.
