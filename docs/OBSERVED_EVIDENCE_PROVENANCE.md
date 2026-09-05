# Observed evidence provenance

FreshCtx can record which files were actually read before a protected action.
This evidence is deliberately separate from the freshness verdict.

```python
from freshctx import ObservedReadCapture

capture = ObservedReadCapture("records")
customer = capture.read_text("customer-42.json")

# ...observe, reason, and run a protected action...

receipt = capture.receipt(
    ctx.correlation,
    candidate_sources=("customer-42.json", "customer-42-old.json"),
    selected_source="customer-42.json",
    cited_sources=("customer-42.json",),
    required_sources=("customer-42.json",),
)
```

`inspected_sources` is generated from successful `read_text` calls. Callers do
not supply it. The receipt links those read events to the action/evidence
correlation ID and the observation IDs checked at the action boundary.

## Independent outcomes

The two results answer different questions:

- `freshness_state` says whether the declared FreshCtx evidence remained
  current at execution.
- `provenance_assessment` says whether the observed reads, selected source, and
  citations satisfy an application-declared source policy.

A source may therefore be `CURRENT` and `INCONSISTENT`. FreshCtx never converts
that combination into a claim that the source was correct.

`required_sources=None` produces `NOT_ASSESSED`. Passing an explicit required
set produces `CONSISTENT` only when every required, selected, and cited source
was observed through the hook; otherwise it produces `INCONSISTENT` with
bounded reason codes.

## Privacy and scope

- Read events contain a generated event ID, a root-relative source ID, and a
  timestamp.
- Source contents, action arguments, credentials, and exception messages are
  not stored in the receipt.
- Reads outside the configured root are rejected.
- The application owns the required-source policy and all semantic judgments.
- This contract records reads made through `ObservedReadCapture`; it cannot
  observe code paths that bypass the hook.

Run the three-path demonstration:

```console
python examples/selection_provenance/run.py
```
