# Freshness boundaries raised by developer feedback

FreshCtx is a runtime freshness guard: it revalidates declared evidence and invalidates affected reasoning before an AI-supported action executes. The practical headline is: **Don't let AI agents act on stale reasoning.**

## FreshCtx and optimistic concurrency control

Optimistic concurrency control (OCC) and compare-and-swap (CAS) predate FreshCtx. FreshCtx applies a similar validate-before-commit discipline to declared reasoning dependencies that may span systems with no shared transaction boundary. It does not claim that OCC is novel and does not create distributed ACID.

Use a database transaction when the reads and writes fit inside one database boundary; it provides stronger guarantees. FreshCtx is useful when reasoning used evidence from files, Git, HTTP, Postgres query results, or safe application-provided MCP readers and the application needs an immediate pre-action recheck. It does not replace a database transaction.

## Freshness is not truth

`CURRENT` means every reachable declared dependency revalidated as equivalent under its configured adapter at check time. It does not mean the source was truthful, the reasoning was correct, the action was authorized, the application was compliant, or downstream code obeyed the result. Undeclared context is not checked.

The four failure classes should remain separate:

- Wrong reasoning: inputs may be current, but the reasoning is incorrect. FreshCtx does not detect this.
- Stale reasoning: declared evidence changed and dependent reasoning becomes `STALE_REASONING`.
- Control failure: the guard cannot reliably decide or write required evidence, commonly producing `UNVERIFIABLE` and a block under the default policy.
- Downstream disobedience: FreshCtx returns block, but code bypasses the protected call and acts anyway.
- Unverifiable context: a dependency is missing, cyclic, unavailable, unsafe to re-read, over a bound, or cannot be validated.

## Detection and recovery

FreshCtx detects freshness and applies its configured policy. Recompute, abort, request renewed approval, or take another recovery path are application or orchestrator decisions. The existing `refresh` policy performs one caller-supplied replacement and recheck; it is not automatic replanning, intent classification, or an approval workflow.

## Current selective invalidation

Evaluation follows only declared reachable edges. Two reasoning nodes depending on different observations are independent: changing one source stales its dependent path, while the other remains `CURRENT`. Multiple reasoning paths can share one observation, and the evaluator memoizes that observation within a check. The current implementation does not infer dependencies or interpret soft context.

Path-scoped Git observation is also selective: an unrelated path change does not change the observed path token. Repository-scoped Git observation does change when repository state changes.

## Control and execution assurance

`Guard.run()` checks and writes `action_allowed` before calling the supplied action. A blocking result does not emit `action_allowed` and does not call that action. FreshCtx cannot prove that other code did not bypass the guard. Independent assurance can compare JSONL `policy_applied` evidence with a separately observed downstream effect, as shown by `examples/opswatch_jsonl_assurance.py`.

JSONL events are local, append-only operational records with the current schema. They are not cryptographically signed, tamper-evident, or proof of compliance.

## Minimal integration

1. Observe only evidence that materially supports the reasoning.
2. Declare the observations on a reasoning node.
3. Immediately before the side effect, call `Guard.run(..., depends_on=[decision])`.
4. Inspect `FreshnessBlocked.result` when blocked.
5. Let the application choose recovery; do not reinterpret `BLOCK` as permission.

```python
with guard(policy="block") as ctx:
    source = observe("approval.json")
    with reasoning("release_decision", [source]) as decision:
        pass
    ctx.run(release, depends_on=[decision])
```

For softer, time-sensitive context, applications can model an explicit clock or validity document through an existing adapter if that document is already authoritative in their system. FreshCtx has no generalized TTL or soft-context ontology; do not imply one.
