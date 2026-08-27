# FreshCtx™

Never let an AI agent reason or act on stale reality.

FreshCtx™ is an independent open-source project initially stewarded by Hyperwise. It is not a proprietary Hyperwise product. The software is model-neutral, framework-neutral, local-first, requires no account, and sends no telemetry.

FreshCtx records source observations, links reasoning to those observations, and revalidates dependencies before a protected action or output.

## Current implementation

The frozen v0.1 contract includes `ObservationToken`, `ReasoningNode`, `DependencyEdge`, and `FreshnessStatus`, with these statuses: `CURRENT`, `STALE_SOURCE`, `STALE_REASONING`, and `UNVERIFIABLE`.

The first v0.1 vertical slice includes:

- `ObservationToken` and `ReasoningNode` data models
- filesystem observation and validation
- Git repository- and path-scoped observation and validation
- transitive freshness evaluation
- `CURRENT`, `STALE_SOURCE`, `STALE_REASONING`, and `UNVERIFIABLE`
- default blocking policy plus `warn` and `allow`
- SQLite and in-memory stores
- local JSONL audit events
- Filesystem, Git, HTTP, Postgres, and MCP adapters

```python
from freshctx import guard, observe, reasoning

with guard(policy="block") as ctx:
    config = observe("config.yaml")
    with reasoning("deployment_target", depends_on=[config]) as decision:
        target = choose_target(config)
    result = ctx.run(agent.run, task, depends_on=[decision])
```

If `config.yaml` changes before the protected boundary, FreshCtx marks the observation `STALE_SOURCE`, the dependent decision `STALE_REASONING`, and raises `FreshnessBlocked`.

`ctx.run()` performs the freshness check and records the allow decision before it invokes the protected function. Use `ctx.protect()` only for output validation where no side effect has already occurred.

## Run the tests

```console
PYTHONPATH=src python -m unittest discover -s tests -v
```

For normal consumer use, install from the repository and run a demo:

```bash
python -m pip install .
python examples/coding_file_drift.py
```

FreshCtx is intended to be Apache-2.0 licensed, model- and framework-neutral, local-first, and free of required accounts or telemetry.

## Developer documentation

- `ARCHITECTURE.md` — components, data flow, trust boundaries, and extension model
- `API.md` — provisional public Python API contract
- `schemas/` — machine-readable v0.1 object contracts
- `adr/` — accepted architecture decisions
- `BACKLOG.md` — issue-ready implementation and release plan
- `PROJECT_STATUS.md` — implemented versus remaining work
- `SPEC.md` — normative, versioned v0.1 specification
- `docs/ADAPTER_CONTRACT.md` — adapter behavior and failure contract
- `docs/SECURITY_MODEL.md` — trust boundaries and fail-closed behavior
- `docs/PERFORMANCE.md` — intended scale and performance boundaries
- `GOVERNANCE.md` and `RELEASING.md` — stewardship and private-to-public release process

## Release checks

```console
python scripts/release_check.py
python -m build
```

The private-phase release workflow is manual and build-only. It tests the release, builds the wheel and source archive, verifies wheel installation, and stores private workflow artifacts. It contains no public publishing job.
