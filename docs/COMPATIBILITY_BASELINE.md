# Compatibility baseline

This record fixes the public implementation at repository SHA `fc682d8f6da65de124b2071fa4fa85b38d72f115` as the baseline for feedback hardening. The work on `hardening/feedback-evidence-baseline` must not change runtime semantics.

## Starting state

- Remote: `https://github.com/Hyperwise-LLC/freshctx.git`
- Default branch: `main`
- Remote HEAD: `fc682d8f6da65de124b2071fa4fa85b38d72f115` (2026-08-30)
- Repository/package version: `0.1.1`
- PyPI version: `0.1.1`; published versions: `0.1.0`, `0.1.1`
- Latest tag and GitHub release: `v0.1.0`; release published 2026-08-28
- Python contract and CI matrix: Python 3.10, 3.11, 3.12, and 3.13 (`requires-python = ">=3.10"`)
- Baseline CI: success for the remote HEAD in GitHub Actions run 33298331608
- Required runtime dependencies: none. Optional extras: `postgres`, `langgraph`, `test`, and `dev`.

## Protected contracts

The public exports in `freshctx.__all__`, signatures documented in `API.md`, the four states, four policies, five bundled adapters, immutable store behavior, JSON Schemas, and JSONL event surface are protected. The authoritative state names are `CURRENT`, `STALE_SOURCE`, `STALE_REASONING`, and `UNVERIFIABLE`. Policy decisions in `CheckResult` are `allow` or `block`; configured policies are `block`, `warn`, `allow`, and `refresh`.

Observation tokens are leaves. Reasoning nodes declare edges to observations or other reasoning nodes. A changed leaf is `STALE_SOURCE`; a reasoning node reachable from it is `STALE_REASONING`. Only the reachable declared graph is evaluated. Missing dependencies, cycles, validation failures, and over-limit conditions are `UNVERIFIABLE`.

The append-only JSONL sink emits the existing event types `guard_started`, `observed`, `protected`, `policy_applied`, and `action_allowed`. Every event uses the existing `schema_version`, `event_id`, `run_id`, `event_type`, `timestamp`, `subject_id`, and `details` fields. This is operational evidence, not a signature or tamper-evident log.

## Preservation proof

`tests/test_compatibility_baseline.py` fixes the minimum sequence:

1. Observe valid evidence and create dependent reasoning.
2. Change the declared evidence.
3. Revalidate at `Guard.run()`.
4. Receive `STALE_REASONING` and `policy_decision == "block"`.
5. Prove the application action was not called.
6. Prove no `action_allowed` event was emitted.

`tests/test_opswatch_jsonl_assurance.py` separately preserves two cases. When an application respects `BLOCK`, no action occurs. When code deliberately bypasses the guarded boundary, the action can occur despite FreshCtx's block; that is downstream disobedience, not an incorrect freshness decision. FreshCtx is a control decision and protected-call helper, not universal execution enforcement.

## Change rule

Documentation, tests, examples, and benchmark measurements in this hardening effort are `NONE` compatibility changes. Any future additive API requires an explicit backward-compatibility case. Experimental ideas are documented only. A change that alters any valid program's result is `SEMANTIC_CHANGE` or `BREAKING` and is outside this effort.
