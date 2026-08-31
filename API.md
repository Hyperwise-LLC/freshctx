# FreshCtx Python API contract

Status: backward-compatible v0.4 contract. Existing v0.1 calls retain their behavior.

## `guard()`

```python
guard(
    policy: str = "block",
    store: Store | None = None,
    run_id: str | None = None,
    audit_path: str | Path = ".freshctx/audit.jsonl",
    validation_workers: int = 1,
    validation_budget_ms: float | None = None,
) -> Guard
```

Creates a run-local enforcement context. Nested guards are permitted only when their dependencies remain isolated. On successful context exit, the guard checks the most recently protected subject. If no subject was protected, it exits without a freshness evaluation.

Supported policies:

- `block`: raise `FreshnessBlocked` for any non-current result.
- `warn`: emit `RuntimeWarning` and permit exit.
- `allow`: permit exit and retain the non-current audit result.
- `refresh`: invoke one registered callback, recheck once, and block unless the replacement subject becomes current.
- `replan`: block the action and return `policy_decision="replan"`.
- `require_approval`: block the action and return `policy_decision="require_approval"`.

Validation remains synchronous and ordered by default. Set `validation_workers` above one to opt into bounded concurrent validation of unique observation tokens from adapters that declare `thread_safe=True`. Custom adapters remain sequential by default.

`validation_budget_ms` defines the decision-validity budget. Checks unfinished at the deadline become `UNVERIFIABLE` with `validation_budget_exceeded`. FreshCtx waits for already-started validators to reach their adapter-specific timeout before returning, discards late results, and leaves no background validation work. The budget is therefore not a hard wall-clock cancellation guarantee.

`Guard.result` contains the final `CheckResult` after automatic enforcement.

## `observe()`

```python
observe(
    locator: str | PathLike,
    adapter: str | None = None,
    **options: object,
) -> ObservationToken
```

Requires an active guard. If `adapter` is omitted, FreshCtx selects `filesystem`. The adapter observes the source, the token is persisted, and an audit event is emitted.

Current adapter options:

```python
observe("config.yaml")
observe("/repo", adapter="git", scope="repository")
observe("/repo", adapter="git", scope="path", path="config.yaml", ref="HEAD")
observe("config.yaml", root=".", max_file_bytes=16 * 1024 * 1024)
observe("quote.json", adapter="http", freshness_strategy="ttl", max_age_seconds=5)
observe("sub_123", adapter="stripe_subscription", api_key="...", fields=("status",), timeout=2.0)
```

The Stripe Subscription adapter accepts `api_key`, `fields`, `include_items`, `api_version`, and a positive `timeout`. Credentials and the transport remain process-local. Persisted tokens contain the Subscription ID, configuration, and fingerprints but not the API key or raw selected values. Reconstruct the observation after restart; otherwise validation safely returns `UNVERIFIABLE`.

Every adapter accepts `freshness_strategy`. Supported values are `exact` (default), `version`, `fingerprint`, `ttl`, `attestation`, and `unverifiable`. `ttl` expires locally after a positive `max_age_seconds`; `unverifiable` deliberately prevents the observation from becoming `CURRENT`. The other values declare adapter-owned comparison semantics. FreshCtx records them but does not invent a universal version, fingerprint, or attestation authority. The adapter remains responsible for returning `equivalent`, `changed`, or `indeterminate` correctly.

Unknown adapters raise the public `ConfigurationError` exception.

## `reasoning()`

```python
reasoning(
    kind: str,
    depends_on: Iterable[ObservationToken | ReasoningNode | ReasoningContext | str],
    metadata: dict | None = None,
) -> ReasoningContext
```

Requires an active guard when the context exits. A successful exit persists one `ReasoningNode`. An exceptional exit does not create a valid node. The completed context may be supplied to `depends_on`; using it before completion raises `FreshCtxError`.

The digest is SHA-256 of canonical JSON over domain `freshctx.reasoning-digest.v1`, reasoning kind, sorted/deduplicated dependency IDs, and redacted metadata. Metadata keys must be strings; dictionary and set ordering are canonical, sets are stored as sorted lists, list ordering is meaningful, and unsupported or non-finite values raise `ConfigurationError`. It stores no raw prompts, hidden reasoning, model output, or source content. The digest identifies the declared reasoning inputs within this contract; it is not a signature, authorization decision, tamper-proof evidence, or proof of correctness. Source freshness always comes from adapter revalidation.

## `Guard.protect()`

```python
Guard.protect(
    value: object = None,
    *,
    depends_on: Iterable[dependency],
    boundary: str = "output",
) -> object
```

Registers a protected output or action. When one dependency is supplied, it becomes the subject directly. Multiple dependencies create a synthetic boundary node. The input `value` is returned unchanged.

Call `protect()` immediately before the real side effect when possible. Guard exit enforcement cannot prevent a side effect that already happened inside the context.

## `Guard.run()`

```python
Guard.run(
    action: Callable,
    *args: object,
    depends_on: Iterable[dependency],
    boundary: str = "action",
    refresh: Callable[[CheckResult], dependency | None] | None = None,
    **kwargs: object,
) -> object
```

This is the required API for protected side effects. It resolves freshness and records the allow decision before invoking `action`. Under `block`, `refresh`, `replan`, or `require_approval`, a non-current result or required audit failure raises `FreshnessBlocked` and the callable is not invoked. Refresh is attempted at most once.

## `Guard.check()`

```python
Guard.check(subject: dependency | None = None) -> CheckResult
```

Evaluates a subject without automatically raising. If omitted, the latest protected subject is used. The caller may inspect `state`, `causes`, `adapter_results`, and `policy_decision`. Adapter evidence includes measured `duration_ms` and the selected freshness strategy.

## Async entry points

`Guard` supports `async with`. `await ctx.check_async(subject)` performs adapter validation outside the event-loop thread, and `await ctx.run_async(action, ..., depends_on=[...])` preserves the same pre-action enforcement boundary for synchronous or awaitable actions. Policies, audit requirements, refresh limits, and fail-closed behavior match `check()` and `run()`.

## `FreshnessBlocked`

```python
class FreshnessBlocked(RuntimeError):
    result: CheckResult
```

Raised by the blocking policy. The message is safe and concise; detailed machine-readable evidence is available through `result`.

## Domain objects

The authoritative fields are defined in `schemas/`. Python dataclasses use immutable instances. IDs are UUID strings in the current implementation; future ULID support must preserve string compatibility.

`ReasoningNode.dependencies` is the canonical graph-edge representation. Stores are immutable by ID: identical repeats are idempotent; different content under an existing ID raises `StorageConflictError` and preserves the original. `SQLiteStore.close()` closes its local connection.

The filesystem adapter accepts `root`, `max_file_bytes` (default 16 MiB), `max_total_bytes` (64 MiB), `max_entries` (10,000), and `follow_symlinks` (false). Followed file symlinks must resolve inside `root`; directory symlink traversal is unsupported. Limit and scope failures validate as `UNVERIFIABLE`. External adapters may keep credentials, readers, or other validation inputs only in process-local state; applications must reconstruct that state after restart.

## Example

```python
from freshctx import FreshnessBlocked, guard, observe, reasoning

try:
    with guard(policy="block") as ctx:
        config = observe("config.yaml")
        with reasoning("deployment_target", [config]) as decision:
            target = choose_target(config)
        ctx.run(deploy, target, depends_on=[decision], boundary="deploy")
except FreshnessBlocked as blocked:
    print(blocked.result.state.value)
```

The original synchronous API remains the compatibility default. Bounded parallel adapter validation is opt-in through `validation_workers`; async entry points are additive.
