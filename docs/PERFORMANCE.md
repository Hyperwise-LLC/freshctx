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

When the decision budget expires, unfinished validations become `UNVERIFIABLE`; cached evidence is never silently treated as current. With the legacy default (`retry_policy=None`), FreshCtx waits for already-started validators to reach their adapter-specific timeout before `check()` returns, then discards late results. No validator continues after that default check returns. `validation_budget_ms` remains a decision-validity budget rather than a hard wall-clock cancellation guarantee in this mode.

An explicit `RetryPolicy` applies a hard return deadline to evidence verification. If an adapter ignores its timeout, a read-only validator thread may finish after `check()` has returned `UNVERIFIABLE`; FreshCtx starts no further verification retry or consequential action after that deadline. Python cannot safely cancel arbitrary blocking I/O, so opt-in adapters must tolerate validation continuing off-thread and must set their own bounded I/O timeouts. Do not use verification callbacks with side effects in this mode.

This opt-in deadline path can call a custom validator on a worker thread even when the adapter is otherwise configured for sequential validation. Validators used with an explicit retry policy must therefore be read-only, safe to invoke off-thread, and use their own bounded I/O timeout. Thread-affine clients should not be used through this path unless the adapter safely marshals validation to its owning thread. Python cannot terminate a validator that ignores its timeout. A `Guard` also holds mutable per-action result, correlation, and protected-parameter state: parallel leaf validation within one check is supported, but sharing the same `Guard` across simultaneous action invocations is not. Create a separate guard per action invocation.

Each adapter result records `duration_ms`. The `policy_applied` audit event records total duration, worker count, and configured budget without changing audit schema version 1.

## Reproducible baseline

```console
PYTHONPATH=src python scripts/benchmark_validation.py --width 8 --workers 4 --delay-ms 25 --iterations 20
```

The harness reports mean, p50, p95, and adapter-call counts for sequential and concurrent checks. It compares releases and graph shapes; it is not a claim about production HTTP, Postgres, or MCP latency.

Production benchmarks should vary graph depth and width, adapter mix, source availability, adapter and total timeouts, concurrency limits, and p50/p95/p99 protected-boundary latency.

For a larger synthetic graph, increase `--width`; the harness raises its graph-depth safety bound only for the generated graph and reports the resulting freshness state so a timing result cannot hide an invalid evaluation:

```console
PYTHONPATH=src python scripts/benchmark_validation.py --width 128 --workers 8 --delay-ms 2 --iterations 20
```

This remains a reproducible engineering baseline, not a production latency claim. Publish real-adapter measurements with environment, source behavior, timeouts, and failure outcomes.
