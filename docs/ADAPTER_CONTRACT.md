# Adapter contract

An adapter exposes `observe(locator, **options) -> ObservationToken` and `validate(token) -> AdapterResult`. Validation must be read-only, bounded by a timeout where external I/O is involved, deterministic for equivalent evidence, and return only `equivalent`, `changed`, or `indeterminate`.

Adapters must not persist plaintext credentials in tokens or audit events. A missing credential, unavailable validator, timeout, permission error, malformed response, unsafe/non-idempotent MCP operation, or unsupported state returns `indeterminate`; it must not be treated as current. Adapter implementations own canonicalization and evidence-specific equivalence rules.
