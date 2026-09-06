# A2A delegation guard

FreshCtx 0.14.0 guards the receiving side of an official A2A Python SDK
`AgentExecutor`. The receiver verifies a bounded delegation receipt and then
revalidates its declared FreshCtx evidence immediately before delegated work begins.

Install:

```bash
python -m pip install 'freshctx[a2a]==0.14.0'
```

Wrap an existing executor:

```python
guarded = FreshCtxA2AExecutor(
    executor,
    receiving_agent="payments-agent",
    depends_on=[approval_decision],
    store=store,
    key_resolver=resolve_process_local_key,
)
```

The sender creates `A2ADelegation`, signs it with `attest_a2a_delegation`, and
places `a2a_delegation_metadata(...)` in A2A request metadata under the advertised
FreshCtx extension URI.

## Outcomes

- A valid receipt plus `CURRENT` evidence allows the wrapped executor to start.
- Missing, malformed, expired, tampered, or wrong-recipient receipts produce a
  native rejected task update before the executor starts.
- `STALE_REASONING` or `UNVERIFIABLE` evidence also produces a rejected update.
- An unrelated source change does not block a delegation that did not declare it.

## Privacy boundary

The record contains agent, skill, task, context, delegation, correlation,
attestation, and observation identifiers. It does not contain prompts, source
contents, credentials, action arguments, or business payloads. Keys remain
process-local and are resolved by issuer and key ID.

The attestation proves possession of the selected key and integrity of the exact
record during its validity window. It does not prove evidence truth, correct source
selection, authorization, safety, or compliance.

Run the cross-protocol demonstration:

```bash
python -m pip install 'freshctx[a2a-mcp]==0.14.0'
python examples/a2a_to_mcp_delegation.py
```
