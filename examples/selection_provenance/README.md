# Observed evidence provenance scenario

This bounded scenario records actual successful file reads through
`ObservedReadCapture`, then keeps inspected, selected, and cited sources separate
from the FreshCtx freshness result.

The fixture directory contains an authoritative ledger and a plausible decoy.
The runner exercises three paths:

1. `exact_filename`: the application supplies the authoritative filename.
2. `discovery_wrong_source`: the decoy is opened and selected while the
   application-declared authoritative source is never inspected.
3. `right_read_wrong_citation`: the authoritative file is opened and selected,
   but the result cites the uninspected decoy.

All selected files remain unchanged, so all FreshCtx results are `CURRENT`.
Provenance is assessed independently: the first path is `CONSISTENT`; the other
two are `INCONSISTENT`. Neither verdict establishes semantic correctness.

Run both paths from the repository root:

```console
python examples/selection_provenance/run.py
```

The runner requires only the normal FreshCtx package. It performs no network
access and writes no persistent files.

## Expected results

| Test path | Inspected source | Cited source | FreshCtx state | Provenance |
| --- | --- | --- | --- | --- |
| Exact filename | authoritative | authoritative | `CURRENT` | `CONSISTENT` |
| Discovery wrong source | decoy | decoy | `CURRENT` | `INCONSISTENT` |
| Right read, wrong citation | authoritative | decoy | `CURRENT` | `INCONSISTENT` |

The discovery result is intentionally `CURRENT`: the selected decoy did not
change after observation. The receipt does not label that source as correct.

## Boundary

- The read hook records root-relative source identities only after successful
  reads. It does not store file contents, action arguments, or credentials.
- Provenance policy is application-declared; the receipt does not certify truth.
- `CURRENT` means the selected file's fingerprint is unchanged.
- `CURRENT` does not mean the selected file was authoritative, complete, or
  correct for the task.
- Each receipt links the read events to the existing action/evidence correlation
  and its FreshCtx observations.
