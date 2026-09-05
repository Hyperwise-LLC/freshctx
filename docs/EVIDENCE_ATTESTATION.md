# Bounded evidence attestation

FreshCtx can seal one exact `ActionEvidenceCorrelation` record with an
application-held HMAC-SHA256 key. The resulting receipt identifies its issuer
and key ID and expires after an application-selected interval.

## What it proves

A verified receipt establishes that:

- the correlation record has not changed since it was signed;
- the signer possessed the configured key;
- the receipt still falls inside its declared time bound.

It does not prove that a source was true, authoritative, or correctly selected.
It does not grant authorization or establish safety, compliance, or the
correctness of reasoning. Attestation verification is separate from the
`CURRENT`, `STALE_REASONING`, and `UNVERIFIABLE` freshness states.

## Example

```python
from freshctx import attest_correlation, verify_attestation

receipt = attest_correlation(
    ctx.correlation,
    issuer="payment-control",
    key_id="local-key-2026-09",
    key=process_local_key,
    ttl_seconds=300,
)

verification = verify_attestation(
    receipt,
    ctx.correlation,
    key=process_local_key,
)
assert verification.valid
assert verification.reason == "verified"
```

Run the complete local demonstration:

```bash
python examples/evidence_attestation.py
```

## Security boundary

- Supply at least 32 bytes of key material from process-local secret storage.
- Persist the public receipt if required, but never persist the key with it.
- Rotate keys through the application-owned `key_id`.
- Use a short validity period appropriate to the protected action.
- Reject `expired`, `payload_mismatch`, `correlation_mismatch`, and
  `signature_mismatch` results.

The built-in HMAC mode is intended for a bounded local trust domain. Systems
requiring independently verifiable signatures, hardware-backed keys, or a
central policy service should place those controls outside this local helper.
