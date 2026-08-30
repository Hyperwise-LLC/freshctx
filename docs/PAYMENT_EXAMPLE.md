# Simulated payment freshness example

`examples/simulated_payment_flow.py` demonstrates a reasoning-to-action race using files only. It does not authorize, approve, submit, or process a real payment.

The declared evidence is available balance, account status, per-payment limit, and approval state. An unrelated support-banner file is deliberately not a dependency. The sequence is explicit: observe evidence → declare reasoning dependencies → change simulated state → reach the action boundary → revalidate → receive a decision and JSONL evidence → let the application honor the policy.

Run all scenarios:

```console
python examples/simulated_payment_flow.py --output-dir /tmp/freshctx-payment --scenario all
```

| Scenario | State change | Expected and current result | Simulated action |
|---|---|---|---|
| A: `current` | None | `CURRENT`, `allow` | Runs |
| B: `balance_changed` | Available balance drops | `STALE_REASONING`, `block` | Does not run |
| C: `approval_changed` | Approval becomes false | `STALE_REASONING`, `block` | Does not run |
| D: `unrelated_changed` | Undeclared support banner changes | `CURRENT`, `allow` | Runs |

Scenario D demonstrates actual selective invalidation: only reachable declared dependencies affect this reasoning node. It does not claim that FreshCtx can discover omitted payment evidence. The JSONL file for each scenario contains the exact current event fields and decision details.
