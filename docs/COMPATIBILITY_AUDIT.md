# v0.1.1 to current Core compatibility audit

## Conclusion

The current Core keeps the v0.1 synchronous API, four-state freshness model, blocking exception, audit event version, and single-worker default. New capabilities are additive or explicitly opt-in.

## Preserved behavior

- `guard()`, `observe()`, `reasoning()`, `Guard.protect()`, `Guard.check()`, and `Guard.run()` retain their v0.1 call shapes.
- The default policy is `block`; a protected stale or unverifiable action raises `FreshnessBlocked` before the callable runs.
- `validation_workers=1` remains the default.
- `FreshnessState` remains an alias of `FreshnessStatus`.
- Audit events remain JSONL schema version 1.
- Existing immutable object IDs cannot be overwritten with different content.

## Additive behavior

- Optional validation concurrency, validation budgets, timing evidence, and response policies.
- Async context, check, and protected-action entry points.
- SQLite schema metadata and forward migration.
- CLI diagnostics and bounded validation reports.

## Store upgrade

Opening a v0.1 SQLite store creates a schema-version table transactionally and records schema version 1. The existing `objects` table and payloads are not rewritten. A store from a newer unsupported schema or a failed integrity check is rejected rather than guessed current.

## Verification

Compatibility tests exercise unchanged v0.1 calls, default behavior, legacy SQLite data, audit version, exception behavior, and alias identity. Clean installation remains part of the release gate.
