# Feedback-driven validation plan

This plan converts public developer feedback into bounded, reproducible evidence. A reported use case is not an independent validation until an external person runs the published scenario and records the result and limitations.

| Scenario | Boundary being tested | Artifact |
| --- | --- | --- |
| Payment balance changes after approval | Revalidate a discrete financial dependency | `examples/payment_balance_change.py` |
| Calendar slot changes after approval | Return `require_approval` without booking | `examples/stale_booking_approval.py` |
| Manual tool pre-flight versus FreshCtx | Compare action outcome, code shape, and audit evidence | `examples/manual_preflight_comparison.py` |
| Deep versus wide dependency graphs | Measure duration, calls, and selective invalidation | `scripts/benchmark_validation.py` |
| Slow or rate-limited sources | Enforce adapter and total validation budgets | Runtime and benchmark tests |
| Soft contextual evidence | Distinguish checkable, TTL, attested, and unverifiable context | Evidence strategies and tests |
| Live voice conversation | Keep semantic output validation separate from source freshness | `examples/voice_agent_live_record.py` |
| Multi-step booking agent | Propagate source staleness through later reasoning | `examples/stale_booking_approval.py` and external review pending |
| Stripe webhook drift | Compare cached webhook state with the authoritative Subscription before action | `examples/stripe_subscription_drift.py`; external review pending |
| Deployment ownership drift | Revalidate job ownership and the smallest blocking dependency set without turning pre-flight into another orchestrator | Bounded external scenario pending |
| Research-brief source drift | Map claims to named sources and flag only claims whose source changed, without interpreting the revised source | Independent `r3` rerun reported four mapped claims, four sources, an empty excluded set, and all fingerprints `CURRENT` after a defensible receipt restored the timing claim; see `docs/INDEPENDENT_RESEARCH_BRIEF_R3.md` |
| Wrong-source selection | Keep source selection provenance separate from source freshness; a selected decoy may remain `CURRENT` without being presented as correct | Experimental exact-filename and discovery paths, versioned receipt schema, ledger fixtures, and regression tests in `examples/selection_provenance/` |
| Agno external dependency drift | Revalidate declared external evidence in Agno's tool-hook chain before the tool body runs | `examples/agno_stale_tool.py` and `tests/test_agno_integration.py`; Agno maintainer review pending |

## Evidence ladder

1. Maintainer-authored unit or scenario test.
2. Clean package installation in an isolated environment.
3. Independent reproduction of the published scenario.
4. External scenario based on another developer's workflow.
5. Production observation with environment, version, limits, and negative outcomes documented.

FreshCtx currently has independent bounded results for the control-versus-behavior scenario and the research-brief `r3` source-mapping rerun. Neither result should be described as broad production validation.
