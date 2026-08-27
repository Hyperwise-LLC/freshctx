# FreshCtx™

Never let an AI agent reason or act on stale reality.

![FreshCtx freshness boundary intercepting stale inputs before an agent action](docs/assets/freshctx-social-preview.png)

FreshCtx™ is an independent open-source project initially stewarded by Hyperwise. It is not a proprietary Hyperwise product. The software is model-neutral, framework-neutral, local-first, requires no account, and sends no telemetry.

FreshCtx is a pre-action freshness and dependency-validation layer for AI agents. It records source observations, links reasoning to those observations, and revalidates declared dependencies before a protected action or output.

## 60-second quickstart

Prerequisites: Python 3.10–3.13 and Git. The Git executable is required by the Git adapter and its compatibility tests.

After FreshCtx v0.1.0 is published to PyPI, install the release package with:

```console
python -m pip install freshctx==0.1.0
```

Until publication—or when working from source—clone and install the repository:

```console
git clone https://github.com/Hyperwise-LLC/freshctx.git
cd freshctx
python -m venv .venv
```

Activate the environment on macOS or Linux:

```console
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On Windows Command Prompt:

```bat
.venv\Scripts\activate.bat
```

Install the source checkout and run the executable quickstart:

```console
python -m pip install .
python examples/quickstart.py
```

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

Run the complete test suite from an installed checkout:

```console
python -m unittest discover -s tests -v
```

FreshCtx is licensed under Apache-2.0, model- and framework-neutral, local-first, and free of required accounts or telemetry.

## Why CI/CD is not enough

GitHub branch protection and CI/CD determine whether a particular commit passed its configured checks. FreshCtx determines whether the specific files, Git state, APIs, database rows, or MCP resources supporting an agent's current action are still valid when that action is about to occur.

FreshCtx does not replace GitHub, pull requests, branch protection, or CI/CD. It closes the reasoning-to-action freshness gap, including for mutable sources outside Git. Path-scoped Git validation prevents an unrelated repository change from invalidating every observation.

Memory tells an agent what it knew. FreshCtx tells it whether that knowledge is still current.

FreshCtx does not prove that reasoning is logically correct or that reality is globally correct. It revalidates declared observations, invalidates reasoning that depends on stale observations, and produces auditable evidence that declared sources were revalidated at decision time. If a source cannot be checked, `UNVERIFIABLE` fails safely according to the configured policy and never silently becomes `CURRENT`.

See [`docs/FAQ.md`](docs/FAQ.md) for concise answers about CI/CD, memory, selective invalidation, compliance controls, and optional adapters.

## Local audit trail

Unless `audit_path` is supplied, FreshCtx appends JSON Lines events to `.freshctx/audit.jsonl`, relative to the process working directory. The file stays local; FreshCtx does not upload audit events or send telemetry.

Set an explicit location when the application has its own data directory:

```python
with guard(audit_path="var/audit/freshctx.jsonl") as ctx:
    ...
```

Each line is one event such as `observed`, `policy_applied`, or `action_allowed`. Treat audit files as application data: restrict access, define retention, and avoid putting them in source control.

## Adapter quick reference

All adapters use the same `observe()` entry point. Revalidation occurs when `ctx.check()`, `ctx.run()`, or a protected boundary evaluates the token or dependent reasoning.

The examples below assume:

```python
from freshctx import guard, observe
```

### Filesystem

```python
with guard(policy="allow") as ctx:
    token = observe("README.md")
    print(ctx.check(token).state.value)
```

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
- `docs/FAQ.md` — product boundaries and common implementation questions
- `GOVERNANCE.md` and `RELEASING.md` — stewardship and private-to-public release process

## Release checks

```console
python -m pip install '.[dev]'
python scripts/release_check.py
python -m build
```

The private-phase release workflow is manual and build-only. It tests the release, builds the wheel and source archive, verifies wheel installation, and stores private workflow artifacts. It contains no public publishing job.
