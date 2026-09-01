# Independent research-brief rerun: r3

Date recorded: 2026-09-01  
External tester: Callum Pierce  
FreshCtx line under test: live document-source validation pattern introduced in 0.5.x

## Question

Can a claim that lacks a defensible source remain excluded, then re-enter the
monitored claim set only after a named source receipt is supplied?

## Reported progression

1. An earlier run mapped four claims but found no defensible source receipt for
   the treatment-timing claim.
2. That claim was excluded rather than reported as `CURRENT` through an
   unsupported mapping.
3. The external tester supplied this receipt:
   - Harmer, Duman & Cowen, *The Lancet Psychiatry* 2017;4(5):409-418
   - DOI: `10.1016/S2215-0366(17)30015-9`
4. `claim-treatment-timing` was remapped to the Harmer receipt instead of the
   C&EN article body.
5. The external tester reran the scenario as `r3` and reported four sources,
   four claims, an empty excluded set, and all four claim results `CURRENT`.

The tester also reported that the C&EN source resolved through the semantic
article path with HTTP 200, and that all three DOI records, including the new
Harmer receipt, resolved through selected Crossref metadata with HTTP 200.

## Bounded result

The rerun demonstrates that the mapping can keep an unsupported claim out of
the monitored set, accept a later named receipt, and restore only that claim to
the declared dependency map. On that same-day rerun, all four monitored source
fingerprints were equivalent to their recorded observations.

`CURRENT` has a deliberately narrow meaning here: the selected source
fingerprint was unchanged. It does not mean FreshCtx proved that the paper is
correct, interpreted the scientific claim, or established that the cited
material supports every formulation of the claim.

## Evidence and limitations

- The result was reported independently by the external tester in the public
  Indie Hackers validation thread.
- The repository records the reported receipt, mapping transition, outcome,
  and limitations; it does not contain the tester's environment or complete
  external audit trail.
- DOI freshness uses selected Crossref metadata. It does not hash publisher
  page layout or independently inspect the paper's full text.
- This is one bounded research-brief scenario, not production, scientific, or
  general document-validation evidence.

## Reproduction surface

- Controlled claim mapping: `examples/document_source_drift.py`
- Live source pattern: `examples/live_document_source_validation.py`
- Live pattern tests: `tests/test_live_document_source_validation.py`

