# Performance boundaries

FreshCtx v0.1 targets local developer and service workflows, not unbounded graphs or bulk indexing. Graph evaluation is linear in the reachable declared dependency graph and defaults to a maximum depth of 100. Filesystem directory observation hashes every descendant file; use narrow paths for large trees. Git commands time out after five seconds. HTTP and Postgres default to five-second timeouts.

Applications should benchmark their own evidence sizes and protected-action latency. Large database results, repositories, or directories should be reduced to stable, purpose-specific evidence before observation.
