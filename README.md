# FreshCtx™

**Stop AI agents from acting on reasoning that is no longer true.**

[![CI](https://github.com/Hyperwise-LLC/freshctx/actions/workflows/ci.yml/badge.svg)](https://github.com/Hyperwise-LLC/freshctx/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/freshctx.svg)](https://pypi.org/project/freshctx/)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10%E2%80%933.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![No telemetry](https://img.shields.io/badge/telemetry-none-17b897)](#local-audit-trail)

![FreshCtx freshness boundary intercepting stale inputs before an agent action](docs/assets/freshctx-social-preview.png)

An agent can make the right decision from accurate information and still take the wrong action: the file, database row, API response, or MCP resource it relied on changed between **reasoning** and **execution**.

FreshCtx is an open-source Python runtime for closing that gap. It records the evidence behind a decision, revalidates the declared dependencies immediately before a protected action, and blocks or flags the action when the reasoning has become stale.

```text
observe evidence → reason from it → revalidate dependencies → act or block
```

- **Model- and framework-neutral** — wrap an existing agent instead of replacing it.
- **Local-first** — no account, hosted control plane, or telemetry.
- **Explicit and auditable** — you choose which evidence matters; FreshCtx records what was checked.
- **Useful beyond files** — adapters cover filesystem, Git, HTTP, Postgres, and safe MCP reads.

FreshCtx is Apache-2.0 software owned and stewarded by Hyperwise LLC as an independent open-source project.

## The failure mode

This is a time-of-check/time-of-use problem for agent reasoning:

1. An agent reads a deployment configuration and decides to deploy to staging.
2. The configuration changes to production while the agent is planning.
3. The agent executes the old staging decision against the new environment.

Prompting cannot reliably close this gap because the relevant state can change after the prompt has been evaluated. FreshCtx adds a freshness boundary immediately before the action.

## See it block stale reasoning

The smallest useful pattern is:

```python
from freshctx import guard, observe, reasoning

with guard(policy="block") as ctx:
    config = observe("config.yaml")

    with reasoning("choose_deployment_target", depends_on=[config]) as decision:
        target = choose_target(config)

    # Revalidates config and the dependent decision before agent.run executes.
    result = ctx.run(agent.run, target, depends_on=[decision])
```

If `config.yaml` changes before `ctx.run()`, FreshCtx marks the observation `STALE_SOURCE`, marks the decision `STALE_REASONING`, and raises `FreshnessBlocked` under the default blocking policy.

**Good first use cases:** deployment agents, coding agents, approval workflows, database-backed operations, browser agents, and MCP workflows that act on mutable resources.

[Read the API](API.md) · [Run the examples](examples) · [Understand the security model](docs/SECURITY_MODEL.md) · [See the roadmap](BACKLOG.md) · [Ask a question](https://github.com/Hyperwise-LLC/freshctx/discussions)

## Quickstart

Prerequisites: Python 3.10–3.13 and Git. The Git executable is required by the Git adapter and its compatibility tests.

Install FreshCtx from PyPI and run the executable quickstart:

```console
python -m venv .venv
source .venv/bin/activate
python -m pip install freshctx
git clone https://github.com/Hyperwise-LLC/freshctx.git
cd freshctx
python examples/quickstart.py
```

On Windows PowerShell, activate the environment with `.\.venv\Scripts\Activate.ps1`; in Command Prompt, use `.venv\Scripts\activate.bat`.

Expected output includes:

```text
DEPLOYED to staging
FreshCtx state: CURRENT
Audit events: 4
```

The complete quickstart is deliberately small:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import MemoryStore, guard, observe, reasoning


def deploy(target: str) -> None:
    print(f"DEPLOYED to {target}")


with TemporaryDirectory() as directory:
    root = Path(directory)
    config = root / "deployment.env"
    audit = root / "freshctx-audit.jsonl"
    config.write_text("TARGET=staging\n", encoding="utf-8")

    with guard(policy="block", store=MemoryStore(), audit_path=audit) as ctx:
        source = observe(config)
        with reasoning("choose_target", depends_on=[source]) as decision:
            target = "staging"
        ctx.run(deploy, target, depends_on=[decision])

    print(f"FreshCtx state: {ctx.result.state.value}")
    print(f"Audit events: {sum(1 for _ in audit.open(encoding='utf-8'))}")
```

### LangGraph

Install the optional integration dependency and run the controlled stale-state scenario:

```console
python -m pip install 'freshctx[langgraph]'
python examples/langgraph_stale_config.py
```

The LangGraph workflow deliberately changes a deployment configuration between planning and its action node. Expected output:

```text
BLOCKED: STALE_REASONING
```

The protected node uses the same framework-neutral boundary:

```python
def deploy_node(state):
    ctx.run(deploy, state["target"], depends_on=[decision])
    return {"deployed": True}
```

## Current implementation

The frozen v0.1 contract includes `ObservationToken`, `ReasoningNode`, `CheckResult`, and `FreshnessStatus`. A `ReasoningNode` carries its canonical, sorted, duplicate-free dependency identifiers; there is no separate public edge object.

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

The following conceptual example shows where FreshCtx fits around an existing agent:

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

## Verify the checkout

```console
python -c "import freshctx; print(freshctx.FreshnessStatus.CURRENT.value)"
```

Run all three reference demos:

```bash
python examples/coding_file_drift.py
python examples/configuration_api_drift.py
python examples/audit_reasoning_drift.py
```

Expected final lines are `STALE_SOURCE`, `STALE_SOURCE`, and `only finding-a invalidated`, respectively.

Run the nine realistic business acceptance scenarios:

```bash
python examples/real_world_success_cases.py --output success-cases.json
```

The command covers banking, e-commerce, audit, insurance, healthcare operations,
procurement, customer service, IT/security, and legal operations. See
[`docs/SUCCESS_CASES.md`](docs/SUCCESS_CASES.md) for the method, results, and limits.

Run the complete test suite from an installed checkout:

```console
python -m pip install '.[test]'
python -m unittest discover -s tests -v
```

FreshCtx is licensed under Apache-2.0, model- and framework-neutral, local-first, and free of required accounts or telemetry.

## License & Commercial Use

FreshCtx is licensed under the [Apache License 2.0](LICENSE). You may use, modify, and distribute the software—including in commercial applications—subject to the license terms. No account, paid plan, or commercial agreement with Hyperwise LLC is required to use FreshCtx.

The software license does not grant permission to use the FreshCtx™ name, logo, or branding in a way that implies endorsement or creates confusion about the source of a modified product. See [TRADEMARKS.md](TRADEMARKS.md).

Hyperwise LLC may separately offer architecture, integration, deployment, managed connectors, organizational controls, and support services. These services are optional, are not required to use the open-source FreshCtx runtime, and remain separate from FreshCtx core. Possible future commercial products are not part of the v0.1 open-source project unless expressly released under its license.

## Why CI/CD is not enough

GitHub branch protection and CI/CD determine whether a particular commit passed its configured checks. FreshCtx determines whether the specific files, Git state, APIs, database rows, or MCP resources supporting an agent's current action are still valid when that action is about to occur.

FreshCtx does not replace GitHub, pull requests, branch protection, or CI/CD. It closes the reasoning-to-action freshness gap, including for mutable sources outside Git. Path-scoped Git validation prevents an unrelated repository change from invalidating every observation.

Memory systems can retain what an agent knew. FreshCtx is not memory: it checks whether reachable, declared evidence still matches its recorded fingerprint.

`CURRENT` proves only that every reachable, declared dependency was successfully revalidated as equivalent under its configured adapter at check time. It does not prove source truth, reasoning correctness, authorization, safety, compliance, or global reality. If a source cannot be checked, `UNVERIFIABLE` follows the configured policy and never silently becomes `CURRENT`.

See [`docs/FAQ.md`](docs/FAQ.md) for concise answers about CI/CD, memory, selective invalidation, compliance controls, and optional adapters.

## Local audit trail

Unless `audit_path` is supplied, FreshCtx appends JSON Lines events to `.freshctx/audit.jsonl`, relative to the process working directory. The file stays local; FreshCtx does not upload audit events or send telemetry.

Set an explicit location when the application has its own data directory:

```python
with guard(audit_path="var/audit/freshctx.jsonl") as ctx:
    ...
```

Each line is one event such as `observed`, `policy_applied`, or `action_allowed`. Treat audit files as application data: restrict access, define retention, and avoid putting them in source control.

SQLite records are written to `.freshctx/freshctx.db` unless a store path is supplied; SQLite may also create `-wal` and `-shm` companion files. Records and audit events can contain absolute local paths. To remove local FreshCtx data, stop every process using the store, then delete the database, its `-wal`/`-shm` companions, and the configured JSONL audit file. Deletion is irreversible; follow your application retention policy first.

## Adapter quick reference

All adapters use the same `observe()` entry point. Revalidation occurs when `ctx.check()`, `ctx.run()`, or a protected boundary evaluates the token or dependent reasoning.

The examples below assume:

```python
from freshctx import guard, observe
```

### Filesystem

```python
with guard(policy="allow") as ctx:
    token = observe("README.md", root=".")
    print(ctx.check(token).state.value)
```

The filesystem adapter streams file hashing and defaults to 16 MiB per file, 64 MiB total, and 10,000 traversed entries. Symlinks are fingerprinted without following them by default. If `follow_symlinks=True`, resolved file symlinks must remain inside `root`; directory symlink traversal is rejected as unsupported. Limit or boundary failures are `UNVERIFIABLE`, never `CURRENT`. Raw file contents are not stored, but absolute paths and safe fingerprint metadata are. Supply only trusted, intentionally scoped paths; FreshCtx does not secret-scan observed files.

### Git

```python
with guard(policy="allow") as ctx:
    token = observe(".", adapter="git", scope="path", path="README.md")
    print(ctx.check(token).state.value)
```

### HTTP

```python
with guard(policy="allow") as ctx:
    token = observe("https://example.com/", adapter="http", timeout=2.0)
    print(ctx.check(token).state.value)
```

Use a read-only endpoint. Authentication headers remain in process-local adapter state and should come from the application's secret store.

### Postgres

Install the optional dependency first:

```console
python -m pip install '.[postgres]'
```

After the public package is available, the equivalent command is `python -m pip install 'freshctx[postgres]==0.1.0'`.

```python
import os

with guard(policy="allow") as ctx:
    token = observe(
        os.environ["DATABASE_URL"],
        adapter="postgres",
        query="SELECT id, status FROM jobs WHERE status = %s",
        params=["ready"],
        ordered=False,
        timeout=2.0,
    )
    print(ctx.check(token).state.value)
```

Postgres validation is read-only. DSNs, raw query text, and parameters are not persisted in observation tokens.

Postgres is an optional observed-source adapter, not a FreshCtx storage backend. Revalidation state such as credentials remains process-local; after restart, the application must reconstruct the configured adapter state or checks safely return `UNVERIFIABLE`.

### MCP

Pass a safe, read-only callable from the application's MCP client:

```python
def read_policy_resource():
    # Replace this body with the application's read-only MCP client call.
    return {"uri": "policy://deployment", "version": 1}


with guard(policy="allow") as ctx:
    token = observe(
        "policy-server",
        adapter="mcp",
        name="read_resource",
        arguments={"uri": "policy://deployment"},
        reader=read_policy_resource,
        safe=True,
    )
    print(ctx.check(token).state.value)
```

Unsafe or non-idempotent MCP operations are `UNVERIFIABLE`; do not use them as validation readers. See `docs/ADAPTER_CONTRACT.md` for the complete extension contract.

FreshCtx does not provide an MCP transport or client. The application supplies and reconstructs the safe-reader callback after process restart. External network calls occur only when the application explicitly selects an external adapter such as HTTP, Postgres, or MCP.

## Project, support, and commercial inquiries

- FreshCtx product site: <https://freshctx.com> (the complete site is being developed separately)
- Source repository: <https://github.com/Hyperwise-LLC/freshctx>
- Hyperwise LLC corporate site: <https://hyperwise.io>
- Community support: see [`SUPPORT.md`](SUPPORT.md)

Community includes the complete v0.1 runtime, five adapters, schemas, examples, and compatibility tests for local developer use. Using FreshCtx in a consequential or regulated workflow? Hyperwise LLC is working with design partners on organizational freshness controls, managed integrations, evidence, and deployment support. Contact `freshctx@hyperwise.io`. This does not announce a hosted service, control plane, enterprise edition, or SLA.

## Developer documentation

- `ARCHITECTURE.md` — components, data flow, trust boundaries, and extension model
- `API.md` — frozen v0.1 Python API contract
- `schemas/` — machine-readable v0.1 object contracts
- `adr/` — accepted architecture decisions
- `BACKLOG.md` — issue-ready implementation and release plan
- `PROJECT_STATUS.md` — implemented versus remaining work
- `SPEC.md` — normative, versioned v0.1 specification
- `docs/ADAPTER_CONTRACT.md` — adapter behavior and failure contract
- `docs/SECURITY_MODEL.md` — trust boundaries and fail-closed behavior
- `docs/PERFORMANCE.md` — intended scale and performance boundaries
- `docs/FAQ.md` — product boundaries and common implementation questions
- `GOVERNANCE.md` and `RELEASING.md` — stewardship and private-to-public release process

## Release checks

```console
python -m pip install '.[dev]'
python scripts/release_check.py
python -m build
```

The private-phase release workflow is manual and build-only. It tests the release, builds the wheel and source archive, verifies wheel installation, and stores private workflow artifacts. It contains no public publishing job.
