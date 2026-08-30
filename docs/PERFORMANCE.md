# Performance boundaries and benchmark method

FreshCtx v0.1 targets local developer and service workflows, not unbounded graphs or bulk indexing. Graph evaluation is linear in the reachable declared dependency graph and defaults to a maximum depth of 100. Filesystem hashing streams 1 MiB chunks and defaults to 16 MiB per file, 64 MiB total, and 10,000 traversed entries. Exceeding a bound is indeterminate and therefore `UNVERIFIABLE`; use narrow trusted roots. Git commands time out after five seconds. HTTP and Postgres default to five-second timeouts.

Applications should benchmark their own evidence sizes and protected-action latency. Large database results, repositories, or directories should be reduced to stable, purpose-specific evidence before observation.

## v0.2 opt-in concurrency

The v0.1-compatible default remains one validation worker. Independent observation tokens can be checked concurrently:

```python
with guard(validation_workers=4, validation_budget_ms=250) as ctx:
    result = ctx.check(decision)
```

Concurrency is bounded and opt-in because validation order and shared client state can matter to custom adapters. Only adapters declaring `thread_safe=True` run in worker threads; every other adapter remains sequential. FreshCtx validates each reachable token at most once per check.

When the decision budget expires, unfinished validations become `UNVERIFIABLE`; cached evidence is never silently treated as current. Python cannot safely kill arbitrary validator threads, so FreshCtx waits for already-started validators to reach their adapter-specific timeout before `check()` returns, then discards those late results. This guarantees that no validator continues in the background after the check returns, but it also means `validation_budget_ms` is a decision-validity budget rather than a hard wall-clock cancellation guarantee. Every external adapter still needs a bounded timeout.

Each adapter result records `duration_ms`. The `policy_applied` audit event records total duration, worker count, and configured budget without changing audit schema version 1.

## Reproducible baseline

```console
PYTHONPATH=src python scripts/benchmark_validation.py --width 8 --workers 4 --delay-ms 25 --iterations 20
```

The harness reports mean, p50, p95, and adapter-call counts for sequential and concurrent checks. It compares releases and graph shapes; it is not a claim about production HTTP, Postgres, or MCP latency.

Production benchmarks should vary graph depth and width, adapter mix, source availability, adapter and total timeouts, concurrency limits, and p50/p95/p99 protected-boundary latency.
