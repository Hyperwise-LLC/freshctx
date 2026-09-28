# FreshCtx 0.17.0 release-candidate qualification

Date: 2026-09-27

Current public release: `0.16.0`

Release candidate: `0.17.0`

Remote baseline: `c84700c361872db43448b72bda37ec560a711eaa`

Prompt 1C accepted result tree: `1c4f49b2b5c0a879bb671b029ebfcf20f52a96b3`

## Scope

This candidate packages the completed Prompt 1C evidence-boundary increment:

- bounded retries for adapter-classified transient evidence-revalidation
  failures;
- consequential action-parameter evidence lineage;
- declared multi-hop and intermediate tool-output lineage;
- fail-closed `UNVERIFIABLE` handling for required missing, malformed, cyclic,
  or unverifiable lineage; and
- caller-supplied operation and attempt observability in action/evidence
  correlation records.

The release finalization changes package/version metadata and release
documentation only. It does not alter the accepted Prompt 1C runtime behavior.

## Compatibility baseline

Prompt 1C is additive and opt in. Existing callers retain the four freshness
states, policy behavior, legacy correlation serialization, and validation path
when the new options are not supplied. Existing tests are not weakened or
removed.

The Baseline C preservation check for this finalization is:

1. the imported Prompt 1C files reproduce the recorded accepted result tree;
2. finalization changes no implementation line other than the source-checkout
   fallback package version;
3. the full FreshCtx regression suite and focused Prompt 1C tests pass after
   the metadata update; and
4. package metadata and source-checkout version both report `0.17.0`.

## Claim boundary

FreshCtx may repeat a read-only evidence verification within explicitly
configured bounds. It does not retry the consequential action. Operation and
attempt fields preserve caller-supplied observability and do not establish
authenticated identity, intent, authorization, retry permission, or attempt
enforcement.

Evidence lineage validates the declared dependency graph, continued evidence
validity, and configured protected-parameter binding. It does not establish
universal provenance, semantic truth, authorization, execution control,
idempotency, or the observed result of an external effect.

## Validation result

- The completed Prompt 1C files reproduced the recorded accepted result tree
  `1c4f49b2b5c0a879bb671b029ebfcf20f52a96b3` before release finalization.
- The complete FreshCtx unittest discovery passed after the 0.17.0 metadata
  update: **213 tests passed**.
- The repository-native release check passed, including the full regression
  discovery, package/source checks, quickstart, checkpoint/resume, async, and
  controlled success-case demonstrations.
- A local `freshctx-0.17.0` wheel and source archive built successfully and
  both passed `twine check`; neither artifact was published.
- The run included all 32 focused execution-boundary tests and all four focused
  framework Prompt 1C tests.
- Existing compatibility tests confirmed legacy correlation serialization,
  legacy validation-budget behavior, the four freshness states, existing
  policies, protected-action behavior, schemas, and adapter behavior.
- No Prompt 1C implementation line changed during finalization. The only
  source-file edit is the source-checkout fallback version from `0.16.0` to
  `0.17.0`.

Baseline C remains intact.

## Publication status

No tag, GitHub release, PyPI publication, npm publication, remote branch, or
production deployment is created by this release-candidate finalization.
