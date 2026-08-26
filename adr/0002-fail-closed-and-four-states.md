# ADR 0002: Fail closed with four explicit freshness states

Status: accepted for v0.1

## Decision

FreshCtx exposes `CURRENT`, `STALE_SOURCE`, `STALE_REASONING`, and `UNVERIFIABLE`. The default blocking policy prevents protected work for every state except `CURRENT`.

## Rationale

Unknown source state is materially different from known staleness and must not be silently accepted. Separating source and reasoning staleness provides a useful causal explanation.

## Consequences

Adapters must return indeterminate outcomes for unavailable or unsafe validation. Applications that prefer availability must explicitly select `warn` or `allow` and retain the non-current audit result.
