# FreshCtx 0.17.0

FreshCtx 0.17.0 extends the pre-action evidence boundary with opt-in,
backward-compatible lineage and verification controls.

## Added

- Bounded retries for adapter-classified transient evidence-revalidation
  failures. Definitive stale results and recognized permanent failures are not
  retried; exhaustion remains fail closed as `UNVERIFIABLE`.
- Consequential action-parameter evidence lineage that binds selected protected
  parameters to declared evidence dependencies and a canonical value digest.
- Optional multi-hop lineage through declared intermediate tool outputs for MCP
  Guard, LangGraph, and Agno. Pre-action-only hooks require upstream output
  instrumentation rather than invented lineage.
- Caller-supplied operation, attempt, parent-attempt, and previous-outcome
  fields in action/evidence correlations for observability.

## Compatibility and boundaries

The new capabilities are additive and opt in. Existing callers preserve their
freshness states, policies, legacy correlation serialization, and validation
path when the new options are not supplied.

Required missing, malformed, cyclic, or unverifiable lineage fails closed as
`UNVERIFIABLE` before the protected action runs, including under `allow` and
`warn` policies.

FreshCtx may retry read-only evidence verification within configured bounds. It
does not retry the consequential action. Supplied operation and attempt fields
are observational; FreshCtx does not infer identity, intent, authorization, or
retry permission from them.

Evidence lineage validates declared dependencies, their continued validity,
and configured protected-parameter binding. It does not establish universal
provenance, semantic truth, authorization, execution control, idempotency, or
the observed result of an external effect.
