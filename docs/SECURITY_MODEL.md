# Security model and failure semantics

FreshCtx protects the interval between observation and action; it does not prove that a source was truthful when observed. The agent process, adapter code, local host, declared dependency graph, and configured audit destination are trust boundaries.

The default `block` policy fails closed for changed, unverifiable, missing, cyclic, or over-depth dependencies and for required audit-write failures. Protected actions are checked before invocation. Files and Git data are read locally; HTTP and Postgres use bounded calls; MCP validation is permitted only for explicitly safe readers. Common secrets are redacted, but applications must avoid placing secrets in locators and metadata.
