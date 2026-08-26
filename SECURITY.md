# Security Policy

## Supported versions

FreshCtx is pre-release software. Security fixes currently target the latest code on the default branch.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability involving credential disclosure, validation bypass, unsafe adapter behavior, audit tampering, or policy enforcement failure.

Until a private reporting address is published, contact the repository owner privately through their Git hosting profile. Include reproduction steps, affected versions, likely impact, and any proposed mitigation.

## Security principles

- The default policy fails closed.
- Validation must not mutate observed systems.
- Unknown conditions become `UNVERIFIABLE`, never `CURRENT`.
- Credentials and common secrets are excluded from stored tokens and audit events.
- FreshCtx requires no hosted account or telemetry.
