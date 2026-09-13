# FreshCtx 0.16.0 qualification contract

Status: **qualification complete; release preparation remains separate**
Release identity: **protected-action qualification and reproducibility**  
Compatibility baseline: public FreshCtx 0.15.0 at `e08f98e50a603fb273fd3bff9bf399e7ebc6f479`

This is an engineering acceptance record, not a claim that 0.16.0 is available.
FreshCtx 0.15.0 remains the current public release until a separate, authorized
release process publishes and independently rechecks 0.16.0.

## Source-of-truth baseline

The baseline was established on 2026-09-13 from a fresh clone of
`https://github.com/Hyperwise-LLC/freshctx.git`. GitHub identified `main` as the
default branch. The remote `main`, tag `v0.15.0`, and GitHub release target all
resolved to:

```text
e08f98e50a603fb273fd3bff9bf399e7ebc6f479
```

`pyproject.toml` and the public PyPI artifact both reported version `0.15.0`.
The GitHub release was published at `2026-09-09T17:03:31Z` and is neither a
draft nor a prerelease. The protected `CI` run for the baseline SHA completed
successfully.
The project declares Python `>=3.10` and classifiers for Python 3.10, 3.11,
3.12, and 3.13. Protected CI exercises those four versions. Work for this
qualification occurs only on:

```text
hardening/0.16-protected-action-qualification
```

The fresh branch had no local/remote difference before qualification began.

## Preserved public contract

The following 0.15.0 behavior is the compatibility baseline.

- Public exports in `freshctx.__all__`, including `guard`, `observe`,
  `reasoning`, stores, result models, errors, provenance records, attestation
  helpers, and `register_adapter`.
- Freshness states: `CURRENT`, `STALE_SOURCE`, `STALE_REASONING`, and
  `UNVERIFIABLE`. `FreshnessState` remains the compatibility alias for
  `FreshnessStatus`.
- Policies: `allow`, `warn`, `refresh`, `block`, `replan`, and
  `require_approval`, with their existing decisions and exception behavior.
- Declared observation and reasoning dependencies, graph traversal,
  shared-dependency evaluation, and selective invalidation as currently
  implemented.
- Built-in adapters: filesystem, Git, HTTP, Postgres, Stripe Subscription, and
  MCP, including each adapter's current validation strategy.
- Existing Agno, LangGraph, OpenAI Agents SDK, Google ADK, ElevenLabs, MCP, and
  A2A integration behavior and native blocking surfaces.
- All 11 public schemas and their packaged copies.
- JSONL event names, fields, redaction, correlation records, and audit-failure
  behavior.
- Existing examples, packaging metadata, and supported Python behavior.

This release may prove those behaviors more thoroughly. It must not silently
change them.

## Change classification gate

Every proposed change must receive one classification before implementation.

| Classification | 0.16 rule |
| --- | --- |
| `NONE` | Permitted for tests, evidence, and documentation that do not affect runtime results. |
| `ADDITIVE` | Requires explicit authorization and proof that existing valid programs retain their results. |
| `EXPERIMENTAL` | Documentation or examples only; no new stability promise. |
| `SEMANTIC_CHANGE` | Do not implement in this release. Record and request a separate decision. |
| `BREAKING` | Do not implement in this release. |

Before any runtime edit, answer: **Does an existing valid program produce the
same result?** If the answer is no or uncertain, stop and classify the finding.
Before any public API addition, prove it is strictly necessary to qualify the
existing runtime. Otherwise, do not add it.

### Current change inventory

| Proposed change | Classification | Decision | Compatibility basis |
| --- | --- | --- | --- |
| Add this qualification contract | `NONE` | Implemented on feature branch | Documentation only |
| Add the machine-readable 0.15.0 baseline record | `NONE` | Implemented on feature branch | Evidence only |
| Require both records in the release-check file inventory | `NONE` | Implemented on feature branch | Release tooling only; runtime is untouched |
| Add qualification regressions for supported paths | `NONE` | Implemented on feature branch | Tests only; no runtime result changed |
| Add a real LangGraph checkpoint/resume example | `NONE` | Implemented on feature branch | Example only; existing wrapper and framework APIs are unchanged |
| Record machine-readable qualification evidence | `NONE` | Implemented on feature branch | Evidence only |
| Correct the public website from 0.9.0 to verified 0.15.0 | `NONE` | Required outside this repository | Accuracy correction; no product behavior change |
| Add or alter a runtime/API to satisfy a path test | Undetermined until evidence exists | Not authorized | Must pass the existing-program-result decision rule |

## Qualification matrix

`QUALIFIED` means an existing executable test already proves the row against
0.15.0. `TO QUALIFY` means evidence must be added before any related runtime
edit. `OUT OF SCOPE` means the runtime or framework does not currently promise
that lifecycle behavior.

| Invocation or risk | Required control | Current evidence | Status | Allowed change |
| --- | --- | --- | --- | --- |
| Ordinary protected invocation | Current runs once; stale and unverifiable do not start; unrelated change runs once | Shared installed-framework conformance matrix | `QUALIFIED` | `NONE` |
| Retry | Every actual invocation of the supported boundary revalidates and does not turn a block into execution | Repeated-boundary regression plus A2A bounded unverifiable retry | `QUALIFIED` for supported FreshCtx and A2A invocation paths; framework-owned automatic retries remain outside the contract | `NONE` |
| Checkpoint resume | Resumed LangGraph execution revalidates immediately before the action | Real `InMemorySaver`, `interrupt`, and `Command(resume=True)` regression and example | `QUALIFIED` for the tested LangGraph path | `NONE` |
| Framework state injection | Only dependencies resolved through the supported state mapping control the boundary; payload remains absent from evidence | Ordinary and resumed LangGraph state-resolver tests; checkpoints persist the reasoning ID, not the runtime object | `QUALIFIED` for tested paths | `NONE` |
| Nested protected calls | Each actual boundary revalidates; current continuations execute once; a blocked inner boundary does not execute | Dedicated current and blocked-inner regressions | `QUALIFIED` | `NONE` |
| Receiving-side delegation | Valid/current starts receiver once; stale, unverifiable, expired, tampered, wrong recipient, or replay does not | A2A integration suite | `QUALIFIED` | `NONE` |
| Shared dependencies | One shared observation is evaluated under existing graph semantics without duplicate or broad invalidation | Explicit two-reasoning-path action-boundary regression validates the shared observation once per boundary | `QUALIFIED` | `NONE` |
| Unrelated dependency change | A protected action remains current when its declared evidence is unchanged | Core, Git path-scope, framework, and A2A tests | `QUALIFIED` | `NONE` |
| Consequential fields | Adapter-specific selected fields and canonicalization behave exactly as currently documented | Git path scope and Stripe selected-field tests | `QUALIFIED` only for current supported strategies | `NONE` |
| ABA history | A monotonic evidence version exposes A→B→A even if the visible value returns to A | `examples/monotonic_evidence_version.py` plus dedicated regression | `QUALIFIED` for the documented monotonic-version strategy | `NONE` |
| External effect | FreshCtx reports the decision at the boundary; the application must honor it | Existing correlation and assurance tests | `QUALIFIED` for control result only | `OUT OF SCOPE` for execution enforcement |

## Required evidence ladder

Passing one layer does not prove the next layer.

1. **Maintainer regression:** deterministic tests against the source tree.
2. **Clean artifact installation:** built wheel and sdist installed outside the
   checkout.
3. **Public-package reproduction:** exact PyPI package installed outside the
   checkout with version and import path recorded.
4. **Independent reproduction:** another developer reports the observed result,
   including failures and differences.
5. **External workflow evidence:** the same boundary is exercised around a
   tool not owned by the maintainer.
6. **Production observation:** an operator records behavior in their real
   environment without turning it into a universal guarantee.

## 0.15.0 baseline results

The untouched source baseline was installed editable with development
dependencies in a new Python 3.11 virtual environment and run through
`python scripts/release_check.py`.

- Python: 3.11.15
- Host: macOS 26.6.2, arm64
- Result: 170 tests passed; 9 tests skipped; release-check examples passed
- OpenAI trace export: skipped because no API key was supplied
- Repository state after the run: clean

The public PyPI wheel was also installed with the public index in two separate
temporary environments while the working directory was outside the checkout.

| Python | Installed version | Import path | Payment example |
| --- | --- | --- | --- |
| 3.11.15 | 0.15.0 | `/private/tmp/freshctx-pypi-015-py311/lib/python3.11/site-packages/freshctx/__init__.py` | `PAYMENT STOPPED: STALE_REASONING; REQUIRE_APPROVAL` |
| 3.13.13 | 0.15.0 | `/private/tmp/freshctx-pypi-015-py313/lib/python3.13/site-packages/freshctx/__init__.py` | `PAYMENT STOPPED: STALE_REASONING; REQUIRE_APPROVAL` |

No source/PyPI behavior discrepancy was observed in these checks. Python 3.10
and 3.12 remain release-matrix requirements; they were not locally available in
this session and must be confirmed by protected CI and artifact tests.

## 0.16.0 qualification results

The qualification branch tests the unchanged 0.15.0 runtime. It does not yet
change the package version or represent a published 0.16.0 artifact.

- Source suite and examples: 177 tests passed and 9 optional-environment tests
  skipped in the mixed development environment. The MCP v2 tests were then run
  in their required separate environment.
- Protected-action additions: six regressions passed for repeated invocation,
  current and blocked nested boundaries, shared dependencies, preserved policy
  results, and ABA detection.
- LangGraph: six existing integration tests plus the new real checkpoint/resume
  test passed. A paused graph resumed after evidence changed, returned
  `STALE_REASONING` with policy decision `block`, and executed the action zero
  times.
- MCP v2: eight native guard tests and the applicable shared conformance test
  passed with MCP 2.2.0. In-process and stdio-subprocess examples produced
  `CURRENT` with one execution and blocked `STALE_REASONING` and
  `UNVERIFIABLE` with zero executions.
- A2A-to-MCP: 18 tests passed, including current, stale, unverifiable, expiry,
  tampering, intent mismatch, concurrent replay, SQLite replay, retry, circuit
  breaking, and the three-agent receiving path.
- Static and dependency checks: Ruff passed, mypy passed for 20 source files,
  and `pip-audit` found no known vulnerabilities.
- Benchmark smoke: five iterations over 16-dependency wide and deep graphs
  remained `CURRENT`; local median processing ranged from 0.688 ms to 0.745 ms
  with one worker and no simulated adapter delay. This is an environment-local
  smoke result, not a performance guarantee or optimization claim.
- Artifacts: wheel and source archive built successfully and passed `twine
  check`. Clean installs outside the checkout passed on Python 3.11.15 (wheel
  and source archive) and Python 3.13.13 (wheel), including the CLI stale demo
  and checkpoint/resume example.

The first local full-suite attempt could not open loopback sockets for two HTTP
tests because of the execution sandbox. The identical suite passed with local
socket permission; this was an environment limitation, not a product change.
A first source-archive check selected the operating system's Python 3.9 and was
correctly rejected by the declared `>=3.10` requirement; rerunning under the
intended Python 3.11 passed.

Machine-readable details are in
`docs/evidence/qualification-v0.16.0.json`. Protected CI remains responsible
for Python 3.10 and 3.12 and for independently repeating repository checks.

## Compatibility decision

`SAFE FOR REVIEW — BEHAVIOR PRESERVED`

This decision covers the qualification changes only. No file under
`src/freshctx`, public API, schema, policy, adapter, freshness rule, or audit
event was changed.

## Explicit exclusions

This qualification does not add or promise:

- a replacement decision-token API, universal evidence lease, or generalized
  projection engine;
- an approval engine or automatic replanning, recovery, or reconciliation;
- an execution gateway, workflow orchestrator, or exactly-once external effect;
- a new framework, async adapter architecture, generalized TTL, or cache;
- a new signing or tamper-evident architecture;
- a memory, context-portability, hosted-control-plane, or truth-guarantee layer.

Application and framework owners continue to own retry, resume, recovery,
authorization, idempotency, orchestration, and whether a returned block is
honored. Qualification will keep that boundary visible in tests and docs.

## Release stop conditions

Stop 0.16 preparation and record the finding if:

- any current valid program changes result;
- an existing public name, schema, event, policy, adapter, or supported Python
  behavior would need to change;
- an unsupported lifecycle path is presented as supported;
- a blocked FreshCtx decision is confused with proof that a downstream system
  could not deliberately ignore it;
- release, tag, PyPI, repository, website, or example claims disagree.

No merge, tag, release, or publication is authorized by this document.
