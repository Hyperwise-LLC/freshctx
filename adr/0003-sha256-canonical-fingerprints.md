# ADR 0003: SHA-256 and canonical serialization

Status: accepted for v0.1

## Decision

FreshCtx uses SHA-256 for content and normalized-record fingerprints. Structured values must be canonically serialized before hashing.

## Rationale

SHA-256 is widely available, deterministic, and sufficiently collision-resistant for freshness comparison. Canonicalization prevents irrelevant representation differences from creating false staleness.

## Consequences

Every adapter must define ordering, encoding, type normalization, and scope. Hashes establish equivalence for FreshCtx purposes; they are not digital signatures or proof of source authenticity.
