# A2A delegation guard

FreshCtx 0.15.0 guards the receiving side of an official A2A Python SDK
`AgentExecutor`. The receiver verifies a bounded delegation receipt and then
revalidates its declared FreshCtx evidence immediately before delegated work begins.

Install:

```bash
python -m pip install 'freshctx[a2a]==0.15.0'
```

Wrap an existing executor:

```python
guarded = FreshCtxA2AExecutor(
    executor,
    receiving_agent="payments-agent",
    depends_on=[approval_decision],
    store=store,
    key_resolver=resolve_process_local_key,
    action_intent=lambda context: {
        "operation": "capture_payment",
        "account_id": selected_account_id(context),
    },
    replay_store=SQLiteDelegationReplayStore(".freshctx/a2a-replay.sqlite3"),
    validation_attempts=3,
    validation_retry_delay_ms=25,
    validation_retry_budget_ms=150,
    circuit_breaker=ValidationCircuitBreaker(failure_threshold=3, open_seconds=30),
)
```

The sender creates `A2ADelegation`, signs it with `attest_a2a_delegation`, and
places `a2a_delegation_metadata(...)` in A2A request metadata under the advertised
FreshCtx extension URI.

The sender supplies the same application-selected action intent to
`A2ADelegation.create(action_intent=...)`. Only its domain-separated SHA-256
digest enters the signed record. The receiver recomputes that digest immediately
before work begins. Raw MCP arguments remain outside FreshCtx metadata.

## Outcomes

- A valid receipt plus `CURRENT` evidence allows the wrapped executor to start.
- Missing, malformed, expired, tampered, or wrong-recipient receipts produce a
  native rejected task update before the executor starts.
- `STALE_REASONING` or `UNVERIFIABLE` evidence also produces a rejected update.
- An unrelated source change does not block a delegation that did not declare it.
- A different action intent, a second use of the same delegation, or concurrent
  replay is rejected before the wrapped executor starts.
- Temporary `UNVERIFIABLE` checks may be retried only within both the configured
  attempt limit and time budget. Exhaustion remains blocked. An open circuit
  rejects immediately; it never converts uncertainty into permission.

## Separate guarantees

| Control | What FreshCtx establishes |
| --- | --- |
| Freshness | The declared evidence still matches its selected adapter strategy. |
| Delegation integrity | The signed receipt is intact, addressed to this receiver, and within its validity window. |
| Intent integrity | The receiver's application-selected action intent matches the digest in the signed receipt. |
| Replay protection | The configured replay store atomically accepts a delegation ID once. |
| Availability | Bounded retries and the circuit breaker limit waiting; they do not promise that evidence will be reachable. |

Parent and root correlation IDs connect audit records. They do not re-anchor,
revoke, or establish the freshness of an entire chain. Every receiving hop
revalidates its own declared evidence. Applications that need revocation must
check a monotonic version or revocation epoch as declared evidence.

For cross-process protection, use `SQLiteDelegationReplayStore` or implement the
same atomic `consume(delegation_id, expires_at)` contract in shared storage. The
memory implementation is intentionally process-local.

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
python -m pip install 'freshctx[a2a-mcp]==0.15.0'
python examples/a2a_to_mcp_delegation.py
python examples/monotonic_evidence_version.py
```
