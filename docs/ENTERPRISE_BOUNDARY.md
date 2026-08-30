# FreshCtx Core and enterprise boundary

FreshCtx Core owns local evidence observation, dependency tracking, freshness evaluation, enforcement, and portable audit events. It remains framework-neutral, local-first, and usable without an account or hosted service.

An enterprise product may add organizational capabilities without weakening or obscuring the open-source control:

- centrally managed evidence and response policies;
- connector configuration and credential governance;
- approval, escalation, and exception workflows;
- fleet-wide latency, source-health, and policy analytics;
- evidence retention, search, export, and compliance reporting;
- deployment controls, tenant isolation, support, and service objectives.

The enterprise layer must consume explicit Core results. It must not redefine `UNVERIFIABLE` as current, silently rerun an agent, or claim that FreshCtx proves source truth, reasoning correctness, authorization, downstream adherence, or regulatory compliance.

## Stable separation

```text
FreshCtx Core                    Enterprise layer
-------------                   ----------------
observe and fingerprint         configure organization policies
track declared dependencies     distribute approved policy templates
revalidate at a boundary        route reapproval and escalation
return freshness and response   monitor fleets and exceptions
write portable audit events     retain, search, and report evidence
```

This separation keeps adoption simple while allowing enterprise governance, assurance, and operations to develop as commercial capabilities.
