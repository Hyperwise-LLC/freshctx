"""Claim-level source drift without asking FreshCtx to interpret a document.

The source labels mirror a bounded external research-brief proposal. This
controlled example does not fetch, reproduce, or assess the scientific claims.
It proves only that a changed source invalidates the claims that declared it.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessState, MemoryStore, guard, observe, reasoning


SOURCE_FILES = {
    "news-report": "news-report-v1",
    "review-doi-10.1038-s41380-022-01661-0": "review-v1",
    "rebuttal-doi-10.1038-s41380-023-02095-y": "rebuttal-v1",
}

CLAIM_SOURCES = {
    "claim-treatment-timing": ("news-report",),
    "claim-review-conclusion": ("review-doi-10.1038-s41380-022-01661-0",),
    "claim-rebuttal-exists": ("rebuttal-doi-10.1038-s41380-023-02095-y",),
    "claim-current-probe-status": ("news-report",),
}


def run_scenario() -> dict[str, str]:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = MemoryStore()
        audit = root / "document-source-audit.jsonl"
        paths = {}
        for source_name, content in SOURCE_FILES.items():
            path = root / f"{source_name}.txt"
            path.write_text(content, encoding="utf-8")
            paths[source_name] = path

        with guard(store=store, audit_path=audit):
            tokens = {name: observe(path) for name, path in paths.items()}
            claims = {}
            for claim_name, source_names in CLAIM_SOURCES.items():
                dependencies = [tokens[source_name] for source_name in source_names]
                with reasoning(claim_name, depends_on=dependencies) as claim:
                    claims[claim_name] = claim

        # The news source changes after the brief was produced. FreshCtx does
        # not decide what the revision means; it identifies dependent claims.
        paths["news-report"].write_text("news-report-v2", encoding="utf-8")

        with guard(policy="allow", store=store, audit_path=audit) as ctx:
            results = {name: ctx.check(claim).state for name, claim in claims.items()}

        return {name: state.value for name, state in results.items()}


if __name__ == "__main__":
    result = run_scenario()
    assert result == {
        "claim-treatment-timing": FreshnessState.STALE_REASONING.value,
        "claim-review-conclusion": FreshnessState.CURRENT.value,
        "claim-rebuttal-exists": FreshnessState.CURRENT.value,
        "claim-current-probe-status": FreshnessState.STALE_REASONING.value,
    }
    for claim_name, state in result.items():
        print(f"{claim_name}: {state}")
