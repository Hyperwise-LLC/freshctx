# Evidence at the action boundary

FreshCtx checks declared evidence immediately before a consequential action runs. The caller chooses which action parameters need evidence protection and supplies the lineage and operation identity when available.

## Four separate concepts

| Concept | Meaning | FreshCtx behavior |
| --- | --- | --- |
| Evidence freshness | Whether an observed source still satisfies its recorded version or freshness strategy | Revalidates declared dependencies and returns `CURRENT`, `CHANGED`, `STALE_REASONING`, or `UNVERIFIABLE` as appropriate |
| Evidence lineage | Which observations and derived nodes support a protected parameter | Traverses declared dependencies to underlying observations; missing, cyclic, or unverifiable required lineage blocks the action |
| Revalidation retry | Another attempt to check evidence after a classified transient verification failure | Applies an optional bounded `RetryPolicy` to verification only |
| Action attempt | One externally supplied attempt to perform the consequential action | Records supplied `ActionAttempt` identity for correlation; does not infer intent, enforce attempt limits, or repeat the action |

“FreshCtx may retry evidence verification after a transient verification failure. FreshCtx does not thereby receive permission to retry the consequential action.”

“FreshCtx validates required evidence and its continued validity. Evidence lineage does not establish universal truth or trustworthiness of arbitrary content.”

## Declare protected parameters

1. Observe the source evidence under a FreshCtx guard.
2. Create derived reasoning nodes with `depends_on` links to their actual source tokens. For a tool output, use a stable invocation ID and output digest in non-sensitive metadata. The digest identifies an output; it does not prove the output is true.
3. Declare only consequential fields in `protected_parameters`, using `ProtectedParameter(dependencies=(...), value_digest=parameter_digest(actual_value))`.
4. Pass actual values through the adapter's value path. FreshCtx hashes them for comparison and does not store raw values in lineage metadata.

For example, a LangGraph action node can take `protected_parameters={"account": ProtectedParameter((lookup_output.id,), parameter_digest("123"))}` and `parameter_values=lambda state: {"account": state["account"]}`. If `lookup_output` depends on an observed customer record, FreshCtx revalidates that record at the action boundary. A missing `account` value or missing required lineage returns `UNVERIFIABLE` and blocks the action.

Protected parameter declarations are opt-in. Unprotected fields do not require lineage. The caller or policy layer selects protected fields; FreshCtx does not decide which business fields are consequential.

When an integration cannot bind a protected value directly to a callable argument, `parameter_values` is an explicit assertion by the integration's trusted extractor. The extractor must return the exact value the action will consume. FreshCtx can compare that value's canonical digest with the declared digest, but it cannot inspect or verify that an opaque closure, custom resolver, or hidden framework state later uses the asserted value. For directly bound named, defaulted, and `**kwargs` arguments, FreshCtx checks the supplied value against the declaration.

## Framework adapters

| Adapter | Actual protected values | Attempt identity | Output lineage |
| --- | --- | --- | --- |
| MCP guard | Reads only named fields from `tools/call` arguments | Accepts caller-supplied `ActionAttempt`; request ID remains the execution correlation ID | Optional `output_lineage(tool_name, result)` and `on_output_node(node)` capture the returned result with declared source dependencies |
| OpenAI Agents input guardrail | Reads only named fields from parsed tool arguments | Accepts caller-supplied `ActionAttempt`; tool-call ID remains the execution correlation ID | Input guardrail has no tool output; no automatic capture |
| LangGraph action node | Uses explicit `parameter_values(state)` resolver | Uses fixed or state-resolved `ActionAttempt` | Optional `output_lineage(state, result)` and `on_output_node(node)` capture a returned result inside the guarded continuation, using caller-declared source dependencies |
| Agno tool hook | Reads only named fields from the hook arguments | Accepts caller-supplied `ActionAttempt` | Optional `output_lineage(function_name, arguments, result)` and `on_output_node(node)` capture the returned result with declared source dependencies |
| Google ADK before-tool callback | Reads only named fields from callback arguments | Accepts caller-supplied `ActionAttempt`; function-call ID remains the execution correlation ID | Before-tool callback has no tool output; no automatic capture |

All five adapters accept optional `retry_policy`. They pass it to the shared pre-action boundary; none retries the consequential tool body. Supply a distinct `ActionAttempt` when an outer workflow replans or retries an action, preserving the same `operation_id` only when the workflow knows it is the same operation. Framework request or call IDs are not treated as operation IDs or attempt counts. If no operation identity is supplied, FreshCtx records it as unavailable.

Without an explicit retry policy, the existing check waits for started validators to finish before returning. With an explicit `RetryPolicy`, the verification deadline can return `UNVERIFIABLE` while a read-only validator that ignores its timeout still runs off-thread. FreshCtx does not start another verification retry or the consequential action after that deadline. Opt-in adapters must tolerate off-thread validation and use bounded I/O timeouts; FreshCtx cannot cancel arbitrary Python I/O.

Automatic intermediate output lineage is unavailable where a hook sees only an impending tool call, as in the OpenAI Agents input guardrail and Google ADK before-tool callback. LangGraph, Agno, and MCP wrappers can capture a returned result when the caller supplies both `output_lineage` and `on_output_node`. The lineage callback returns a stable invocation ID and actual source dependencies; FreshCtx records the returned value's digest and passes its reasoning node to the sink. Chain that node into later output nodes and protected parameters. Do not invent source dependencies from a parameter name or trust a hash as proof of content accuracy.
