# FreshCtx Python API contract

Status: provisional v0.1. Breaking changes are allowed until v0.1 is released, but changes must update this document, schemas, tests, and changelog together.

## `guard()`

```python
guard(
    policy: str = "block",
    store: Store | None = None,
    run_id: str | None = None,
    audit_path: str | Path = ".freshctx/audit.jsonl",
) -> Guard
```

Creates a run-local enforcement context. Nested guards are permitted only when their dependencies remain isolated. On successful context exit, the guard checks the most recently protected subject. If no subject was protected, it exits without a freshness evaluation.

Supported policies:

- `block`: raise `FreshnessBlocked` for any non-current result.
- `warn`: emit `RuntimeWarning` and permit exit.
- `allow`: permit exit and retain the non-current audit result.
- `refresh`: invoke one registered callback, recheck once, and block unless the replacement subject becomes current.

`Guard.result` contains the final `CheckResult` after automatic enforcement.

## `observe()`

```python
observe(
    locator: str | PathLike,
    adapter: str | None = None,
    **options: object,
) -> ObservationToken
```

Requires an active guard. If `adapter` is omitted, v0.1 selects `filesystem`. The adapter observes the source, the token is persisted, and an audit event is emitted.

Current adapter options:

```python
observe("config.yaml")
observe("/repo", adapter="git", scope="repository")
observe("/repo", adapter="git", scope="path", path="config.yaml", ref="HEAD")
```

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

The current digest covers the reasoning kind and metadata, not raw prompts or model output. This behavior is provisional and must be finalized before v0.1.

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

This is the required API for protected side effects. It resolves freshness and records the allow decision before invoking `action`. Under `block` or `refresh`, a non-current result or required audit failure raises `FreshnessBlocked` and the callable is not invoked. Refresh is attempted at most once.

## `Guard.check()`

```python
Guard.check(subject: dependency | None = None) -> CheckResult
```

Evaluates a subject without automatically raising. If omitted, the latest protected subject is used. The caller may inspect `state`, `causes`, `adapter_results`, and `policy_decision`.

## `FreshnessBlocked`

```python
class FreshnessBlocked(RuntimeError):
    result: CheckResult
```

Raised by the blocking policy. The message is safe and concise; detailed machine-readable evidence is available through `result`.

## Domain objects

The authoritative fields are defined in `schemas/`. Python dataclasses use immutable instances. IDs are UUID strings in the current implementation; future ULID support must preserve string compatibility.

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

## Known v0.1 API work

- Decide and test asynchronous context behavior.
- Finalize reasoning digest semantics and redaction options.
