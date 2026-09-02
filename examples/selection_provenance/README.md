# Experimental source-selection provenance scenario

This bounded scenario demonstrates an adjacent failure mode that FreshCtx Core
does not claim to solve: an agent can select the wrong source before freshness
validation begins.

The fixture directory contains an authoritative ledger and a plausible decoy.
The runner exercises two paths:

1. `exact_filename`: the application supplies the authoritative filename.
2. `discovery`: a deterministic filename-based discovery rule selects the
   plausible decoy without opening the authoritative ledger.

Both selected files remain unchanged, so both FreshCtx observations are
`CURRENT`. The experimental `SelectionReceipt` records how the source was
selected and links to the resulting FreshCtx observation. It deliberately sets
`sourceCorrectness` to `NOT_ASSESSED`.

Run both paths from the repository root:

```console
python examples/selection_provenance/run.py
```

The runner requires only the normal FreshCtx package. It performs no network
access and writes no persistent files.

## Expected results

| Test path | Selected source | Authoritative ledger opened | FreshCtx state | Source correctness |
| --- | --- | --- | --- | --- |
| Exact filename | `authoritative_ledger_2026.csv` | Yes | `CURRENT` | `NOT_ASSESSED` |
| Discovery | `2026_operations_ledger_FINAL.csv` | No | `CURRENT` | `NOT_ASSESSED` |

The discovery result is intentionally `CURRENT`: the selected decoy did not
change after observation. The receipt does not label that source as correct.

## Boundary

- The receipt records selection provenance; it does not certify the selection.
- `CURRENT` means the selected file's fingerprint is unchanged.
- `CURRENT` does not mean the selected file was authoritative, complete, or
  correct for the task.
- This experiment is not part of the stable FreshCtx Core API.
