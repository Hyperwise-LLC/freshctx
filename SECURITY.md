# Security Policy

## Supported version

Security fixes target the latest `0.1.x` release and, before publication, the latest code on the default branch. Older pre-release commits are not supported.

## Report a vulnerability

Email `security@hyperwise.io`. Do not use a public GitHub issue for an undisclosed vulnerability. This address is for security reports, not general support.

Include the affected version or commit, component, reproduction steps, likely impact, and any suggested mitigation. Do not include credentials, production data, or sensitive customer information unless it is strictly necessary and agreed in advance.

Hyperwise LLC targets acknowledgment within three business days. This is a response target, not a contractual service level. Please allow time for investigation and coordinated disclosure before publishing details.

## Security principles

- The default policy fails closed.
- Validation must not mutate observed systems.
- Unknown conditions become `UNVERIFIABLE`, never `CURRENT`.
- Common credentials are redacted, but callers remain responsible for safe inputs and storage access.
- FreshCtx requires no hosted account and sends no telemetry.
