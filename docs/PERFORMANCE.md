# Performance boundaries

FreshCtx v0.1 targets local developer and service workflows, not unbounded graphs or bulk indexing. Graph evaluation is linear in the reachable declared dependency graph and defaults to a maximum depth of 100. Filesystem hashing streams 1 MiB chunks and defaults to 16 MiB per file, 64 MiB total, and 10,000 traversed entries. Exceeding a bound is indeterminate and therefore `UNVERIFIABLE`; use narrow trusted roots. Git commands time out after five seconds. HTTP and Postgres default to five-second timeouts.

Applications should benchmark their own evidence sizes and protected-action latency. Large database results, repositories, or directories should be reduced to stable, purpose-specific evidence before observation.
