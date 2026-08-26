# ADR 0001: Local-first SQLite storage

Status: accepted for v0.1

## Decision

FreshCtx uses SQLite as its default persistent store and an in-memory implementation for tests.

## Rationale

SQLite requires no account or service, supports atomic transactions and WAL mode, is available in Python's standard library, and keeps FreshCtx model- and framework-neutral.

## Consequences

The first release targets single-host execution. Multi-host consistency and distributed coordination are non-goals. Schema migrations and supported concurrency behavior must be tested before release.
