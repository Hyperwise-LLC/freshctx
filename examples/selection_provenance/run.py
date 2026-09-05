"""Demonstrate observed reads, selection, and citation as separate facts."""

from __future__ import annotations

import json
from pathlib import Path

from freshctx import FreshnessStatus, MemoryStore, ObservedReadCapture, guard, observe

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
AUTHORITATIVE_LEDGER = "authoritative_ledger_2026.csv"
DECOY_LEDGER = "2026_operations_ledger_FINAL.csv"


def run_path(path_name: str) -> dict[str, object]:
    capture = ObservedReadCapture(FIXTURES)
    candidates = tuple(sorted(path.name for path in FIXTURES.glob("*.csv")))
    if path_name == "exact_filename":
        selected, cited = AUTHORITATIVE_LEDGER, (AUTHORITATIVE_LEDGER,)
    elif path_name == "discovery_wrong_source":
        selected, cited = DECOY_LEDGER, (DECOY_LEDGER,)
    elif path_name == "right_read_wrong_citation":
        selected, cited = AUTHORITATIVE_LEDGER, (DECOY_LEDGER,)
    else:
        raise ValueError(f"unsupported path: {path_name}")

    capture.read_text(selected)
    store = MemoryStore()
    with guard(store=store):
        observation = observe(FIXTURES / selected)
    with guard(policy="allow", store=store) as ctx:
        ctx.run(lambda: None, depends_on=[observation], boundary="prepare_report")
    result = ctx.result

    receipt = capture.receipt(
        ctx.correlation,
        candidate_sources=candidates,
        selected_source=selected,
        cited_sources=cited,
        required_sources=(AUTHORITATIVE_LEDGER,),
    )
    return {
        "path": path_name,
        "freshnessStatus": result.state.value,
        "provenanceAssessment": receipt.provenance_assessment.value,
        "receipt": receipt.to_dict(),
    }


def run_scenario() -> dict[str, object]:
    names = ("exact_filename", "discovery_wrong_source", "right_read_wrong_citation")
    return {"scenario": "observed_evidence_provenance", "results": {name: run_path(name) for name in names}}


if __name__ == "__main__":
    outcome = run_scenario()
    assert all(result["freshnessStatus"] == FreshnessStatus.CURRENT.value for result in outcome["results"].values())
    print(json.dumps(outcome, indent=2, sort_keys=True))
