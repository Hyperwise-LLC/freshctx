# Action/evidence correlation contract

Status: versioned additive contract, pending release

Contract identifier: `freshctx.action_evidence_correlation.v1`

## Purpose

Every `Guard.run()` and `Guard.run_async()` call produces one portable record
that identifies the protected action and the evidence graph checked immediately
before it. The same record shape is used for an allowed boundary and a blocked
boundary.

The contract answers:

- which run and optional framework execution initiated the check;
- which action and boundary were protected;
- which dependencies the caller declared;
- which reasoning nodes and observations were reachable;
- which declared identifiers could not be resolved;
- which freshness state and application policy decision resulted; and
- whether the boundary allowed or blocked continuation.

It does not attest that the evidence was authoritative, selected correctly, or
interpreted correctly. It does not record whether an allowed continuation later
succeeded.

## Runtime access

```python
with guard(store=store, run_id="framework-call-123") as ctx:
    ctx.run(send_payment, depends_on=[decision], boundary="payment.execute")

correlation = ctx.correlation
print(correlation.to_dict())
```

When a blocking policy raises `FreshnessBlocked`, the same record is available
from `blocked.correlation` and `ctx.correlation`:

```python
try:
    with guard(store=store) as ctx:
        ctx.run(send_payment, depends_on=[decision])
except FreshnessBlocked as blocked:
    correlation = blocked.correlation
```

`PreActionBoundary.last_correlation` exposes the record to framework bridges
after synchronous or asynchronous invocation.

## Fields

| Field | Meaning |
| --- | --- |
| `correlation_id` | Unique identity for this boundary evaluation. |
| `run_id` | FreshCtx audit run containing the evaluation. |
| `execution_id` | Optional caller-supplied framework call or run identity. |
| `runtime` | Framework/runtime identity when supplied by the pre-action contract. |
| `action` | Protected action identity, preferring the framework action name. |
| `boundary` | Developer-visible action boundary. |
| `subject_id` | Exact graph subject evaluated by FreshCtx. |
| `declared_dependency_ids` | Dependencies supplied to the protected call. |
| `reasoning_ids` | Reachable stored reasoning nodes. |
| `observation_ids` | Reachable stored observations. |
| `unresolved_dependency_ids` | Referenced graph identifiers absent from the store. |
| `freshness_state` | FreshCtx freshness result only. |
| `policy_decision` | Application-selected response to that result. |
| `boundary_outcome` | Whether continuation was allowed or blocked. |
| `checked_at` | Timestamp from the corresponding `CheckResult`. |
| `created_at` | Correlation-record creation timestamp. |

The authoritative JSON Schema is
`schemas/action-evidence-correlation.schema.json` and is also included in the
installed package.

## Audit behavior

The runtime writes the record as the details of an
`action_evidence_correlated` JSONL audit event before an allowed continuation
starts. A blocking result is correlated before control returns to the caller.

Action arguments, source contents, prompts, model output, credentials, and
business payloads are not fields in this contract. Normal FreshCtx redaction is
also applied before the audit event is written.

## Relationship to selection provenance

This contract can link a future selection-provenance receipt to the action that
consumed its FreshCtx observation. The two verdicts remain separate:

- action/evidence correlation records freshness and policy enforcement;
- selection provenance records what was inspected, selected, and cited;
- neither converts `CURRENT` into a claim of source correctness.
