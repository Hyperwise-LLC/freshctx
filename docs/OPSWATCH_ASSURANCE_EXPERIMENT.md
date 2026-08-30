# FreshCtx JSONL assurance experiment

This bounded experiment separates a FreshCtx control decision from independent
observation of downstream agent behavior. It uses only local files and the
normal FreshCtx JSONL audit trail.

## Question

Can an independent, read-only assurance layer determine whether an agent
respected a FreshCtx block after a declared dependency changed?

## Scenario

1. The agent observes an approval record for `vendor-a`.
2. The agent derives a release decision from that record.
3. The approval changes to an unapproved `vendor-b` before execution.
4. FreshCtx revalidates the declared dependency and returns
   `STALE_REASONING` with a `block` policy decision.
5. The bounded runner either respects the block or deliberately bypasses the
   protected boundary.
6. An independent observer compares the JSONL decision with the downstream
   effect.

The violating mode is intentionally noncompliant test behavior. It does not
represent a FreshCtx bypass inside `ctx.run`; it calls the simulated action
outside the protected boundary so an assurance tool has a known failure to
detect.

## Run both outcomes

From a FreshCtx repository checkout with the package installed:

```console
python examples/opswatch_jsonl_assurance.py \
  --output-dir /tmp/freshctx-opswatch-respect \
  --behavior respect

python examples/opswatch_jsonl_assurance.py \
  --output-dir /tmp/freshctx-opswatch-violate \
  --behavior violate
```

Each output directory contains:

- `freshctx-audit.jsonl`: the unmodified FreshCtx audit stream;
- `approval.json`: the dependency after the simulated concurrent change;
- `downstream-effect.json`: present only when the action executed; and
- `downstream-observation.json`: the bounded observer's verdict.

## Expected verdicts

| Runner behavior | FreshCtx decision | Downstream effect | Assurance verdict |
| --- | --- | --- | --- |
| `respect` | `block` | absent | `PASS_AGENT_RESPECTED_BLOCK` |
| `violate` | `block` | present | `FAIL_AGENT_ACTED_AFTER_BLOCK` |

For both modes, the audit trail should contain one `policy_applied` event whose
details include `state: STALE_REASONING` and `policy_decision: block`. It should
not contain `action_allowed`.

## OpsWatch boundary

OpsWatch can remain read-only for this first experiment. Its input is the
FreshCtx JSONL trail plus independently observed downstream behavior. FreshCtx
answers whether the decision was still valid at the action boundary; OpsWatch
answers whether the agent respected that result.

Results should be published whether the expected verdict is reproduced or not.
