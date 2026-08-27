# FreshCtx™ validated reference scenarios

FreshCtx v0.1 was exercised against nine realistic business workflows. These are controlled acceptance tests—not customer deployments or claims of production outcomes. They demonstrate that FreshCtx detects changed or unreachable evidence, invalidates only dependent reasoning, and prevents the protected action from executing.

## Test method

Each scenario records multiple sources, builds a decision from explicit dependencies, changes or disconnects one source while the workflow is underway, and then attempts the consequential action. A case passes only when:

- changed evidence is `STALE_SOURCE`, or unreachable evidence is `UNVERIFIABLE`;
- dependent reasoning is `STALE_REASONING` or `UNVERIFIABLE`;
- unrelated evidence remains `CURRENT`;
- the protected action is blocked before its callback executes; and
- local audit events record the checks.

Run the repeatable suite with:

```bash
python examples/real_world_success_cases.py --output success-cases.json
python -m unittest tests.test_success_cases -v
```

## Validated cases

| Domain | Decision and intervening change | Verified outcome |
|---|---|---|
| Banking and payments | A $240,000 supplier wire was approved from account, beneficiary, risk, and dual-approval evidence. Before release, the source account was frozen and placed on legal hold. | Account became `STALE_SOURCE`; wire reasoning became `STALE_REASONING`; the release callback did not execute. A second version runs against disposable Postgres. |
| E-commerce | A same-day order attempted to reserve 12 units using inventory, price, fraud, and carrier-capacity evidence. Inventory fell from 24 available units to 3. | Inventory and dependent fulfillment reasoning became stale; fraud evidence remained current; reservation was blocked. |
| Audit and assurance | Three findings used separate policy and evidence files. The retention policy changed after the findings were prepared. | Only the retention-dependent finding became stale. Access-control and backup findings remained current; issuance of the combined pack was blocked. |
| Insurance | A $38,400 property settlement relied on active coverage, claim approval, fraud clearance, and supervisor approval. The policy entered suspended review. | Coverage and settlement reasoning became stale; unrelated fraud evidence remained current; payment was blocked. |
| Healthcare operations | Appointment confirmation relied on payer authorization and scheduling evidence. The authorization service became unreachable. | Authorization and its dependent reasoning remained `UNVERIFIABLE`—never `CURRENT`; scheduling was blocked safely. No clinical recommendation was modeled. |
| Enterprise procurement | A $186,000 purchase order relied on vendor, quote, budget, and approval evidence. The quote rose to $214,000, crossing the approval threshold. | Quote and purchase reasoning became stale; vendor evidence remained current; PO issuance was blocked. |
| Customer service | A $1,249 refund relied on order, return, refund-ledger, and policy evidence. Another channel recorded a refund before execution. | Refund-ledger evidence and dependent reasoning became stale; unrelated order evidence remained current; the duplicate refund was blocked. |
| IT and security operations | A firewall remediation plan depended on a scoped Git policy file and current scan evidence. An unrelated README commit occurred, followed by a policy change. | The unrelated commit caused no invalidation. The policy commit made only the dependent remediation stale, and execution was blocked. |
| Legal operations | Record disposition relied on retention, matter, approval, and legal-hold evidence. A hold was activated before deletion. | Legal-hold evidence and disposition reasoning became stale; unrelated retention evidence remained current; deletion was blocked. |

## What these results establish

The tests establish the expected FreshCtx control behavior in repeatable reference workflows: fail safely, preserve dependency boundaries, and stop stale actions. They do not establish regulatory compliance, production-scale performance, business savings, or fitness for a specific customer environment. Organizations should add their own adapters, policies, threat modeling, and end-to-end acceptance tests before production use.

## Evidence

- Controlled-suite result: `docs/evidence/success-cases-v0.1.json`
- Live Postgres banking result: `docs/evidence/banking-postgres-v0.1.json`
- Executable scenarios: `examples/real_world_success_cases.py`
- Assertions: `tests/test_success_cases.py`
- Live database runner: `scripts/banking_postgres_success_case.py`

Evidence files contain synthetic records only. They contain no customer data, credentials, DSNs, hostnames, or private URLs.
