# Security model and failure semantics

FreshCtx protects the interval between observation and action; it does not prove that a source was truthful when observed. The agent process, adapter code, local host, declared dependency graph, and configured audit destination are trust boundaries.

The default `block` policy fails closed for changed, unverifiable, missing, cyclic, over-depth, over-limit, or out-of-scope dependencies and for required audit-write failures. Protected actions are checked and the allow event is written before invocation. Files and Git data are read locally; HTTP and Postgres use bounded calls; MCP validation is permitted only for explicitly safe, application-provided readers. External calls occur only through explicitly selected adapters.

`CURRENT` proves only successful equivalence checks for all reachable declared dependencies under configured adapters at check time. It does not prove source truth, reasoning correctness, authorization, safety, compliance, or global reality. An adapter exception or unavailable runtime validator becomes `UNVERIFIABLE` and never silently becomes `CURRENT`.

Common secrets are redacted, but FreshCtx does not secret-scan all observed sources. Applications must avoid secrets in locators and metadata, restrict access to the local SQLite/audit files, and reconstruct process-local external adapter credentials and readers after restart.
