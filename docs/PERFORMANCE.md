# Performance boundaries

FreshCtx v0.1 targets local developer and service workflows, not unbounded graphs or bulk indexing. Graph evaluation is linear in the reachable declared dependency graph and defaults to a maximum depth of 100. Filesystem hashing streams 1 MiB chunks and defaults to 16 MiB per file, 64 MiB total, and 10,000 traversed entries. Exceeding a bound is indeterminate and therefore `UNVERIFIABLE`; use narrow trusted roots. Git commands time out after five seconds. HTTP and Postgres default to five-second timeouts.

Applications should benchmark their own evidence sizes and protected-action latency. Large database results, repositories, or directories should be reduced to stable, purpose-specific evidence before observation.

## Reproducible baseline

Run the committed harness without changing runtime code:

```console
python scripts/benchmark_baseline.py --iterations 20 --depth 50 --width 100 --output docs/evidence/benchmark-baseline.json
```

The 2026-08-30 baseline used repository SHA `fc682d8f6da65de124b2071fa4fa85b38d72f115`, Python 3.13.13, macOS 26.5.2, and arm64. It used `time.perf_counter_ns`, excluded two warmups, retained normal JSONL writes, did not flush filesystem caches, and measured one warm process. Results are milliseconds per check:

| Category | Topology/configuration | Median | p95 |
|---|---|---:|---:|
| Deep graph traversal | depth 50, one leaf | 0.164 | 0.188 |
| Wide graph traversal | 100 unique leaves | 2.337 | 2.451 |
| Shared dependency paths | 100 reasoning paths, one shared leaf | 1.264 | 1.341 |
| Filesystem validation | 4 KiB file | 0.221 | 0.237 |
| Git validation | path scope | 27.859 | 31.620 |
| HTTP validation | loopback server; request latency included | 0.405 | 0.508 |
| MCP validation | in-process safe reader; no transport latency | 0.420 | 0.570 |

The harness separates synthetic internal graph processing from adapter validation. The stable internal adapter exists only to isolate traversal cost; it is not a product adapter. Filesystem, Git, HTTP, and MCP rows exercise the existing implementations. HTTP deliberately uses loopback. MCP benchmarks the current application-provided safe-reader contract, not a network transport.

Postgres was not measured because no real disposable Postgres service was available. The existing Postgres contract remains covered by correctness tests using its connector seam, but a performance number is not fabricated. Results are single-machine baseline evidence, not capacity claims, and external production latency will dominate HTTP, Postgres, and transported MCP use. Raw distributions and environment metadata are in `docs/evidence/benchmark-baseline.json`.
