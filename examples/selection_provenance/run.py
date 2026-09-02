"""Reproduce exact-filename and wrong-source discovery paths.

This example records how a source was selected, then asks FreshCtx only the
question FreshCtx is designed to answer: has that selected source changed?
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from freshctx import FreshnessStatus, MemoryStore, guard, observe
from freshctx.model import utcnow


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
AUTHORITATIVE_LEDGER = "authoritative_ledger_2026.csv"
REQUEST = "Use the final 2026 operations ledger to prepare the report."
SCHEMA_VERSION = "freshctx.selection_receipt.experimental.v1"


@dataclass(frozen=True)
class SelectionReceipt:
    """Experimental audit record; it does not certify source correctness."""

    selection_mode: str
    request: str
    candidate_sources: tuple[str, ...]
    inspected_sources: tuple[str, ...]
    selected_source: str
    selection_reason: str
    observation_id: str
    source_correctness: str = "NOT_ASSESSED"
    created_at: str = ""
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        return {
            "schemaVersion": value["schema_version"],
            "selectionMode": value["selection_mode"],
            "request": value["request"],
            "candidateSources": list(value["candidate_sources"]),
            "inspectedSources": list(value["inspected_sources"]),
            "selectedSource": value["selected_source"],
            "selectionReason": value["selection_reason"],
            "observationId": value["observation_id"],
            "sourceCorrectness": value["source_correctness"],
            "createdAt": value["created_at"],
        }


def _candidate_names() -> tuple[str, ...]:
    return tuple(sorted(path.name for path in FIXTURES.glob("*.csv")))


def _discover(candidates: tuple[str, ...]) -> tuple[str, str]:
    """Apply a deliberately shallow filename heuristic used by the scenario."""

    def score(name: str) -> tuple[int, str]:
        lowered = name.lower()
        points = sum(
            weight
            for term, weight in (("final", 4), ("operations", 3), ("ledger", 2), ("2026", 1))
            if term in lowered
        )
        return points, name

    selected = max(candidates, key=score)
    return selected, "highest filename match for final, operations, ledger, and 2026"


def run_path(selection_mode: str) -> dict[str, object]:
    candidates = _candidate_names()
    if selection_mode == "exact_filename":
        selected = AUTHORITATIVE_LEDGER
        selection_reason = "application supplied the exact authoritative filename"
    elif selection_mode == "discovery":
        selected, selection_reason = _discover(candidates)
    else:
        raise ValueError(f"unsupported selection mode: {selection_mode}")

    inspected = (selected,)
    store = MemoryStore()
    with guard(store=store):
        observation = observe(FIXTURES / selected)

    receipt = SelectionReceipt(
        selection_mode=selection_mode,
        request=REQUEST,
        candidate_sources=candidates,
        inspected_sources=inspected,
        selected_source=selected,
        selection_reason=selection_reason,
        observation_id=observation.id,
        created_at=utcnow(),
    )

    with guard(policy="allow", store=store) as ctx:
        result = ctx.check(observation)

    return {
        "path": selection_mode,
        "fixtureExpectedSource": AUTHORITATIVE_LEDGER,
        "selectedSourceMatchesFixture": selected == AUTHORITATIVE_LEDGER,
        "realSourceOpened": AUTHORITATIVE_LEDGER in inspected,
        "freshnessStatus": result.state.value,
        "freshnessMeaning": "selected source fingerprint is unchanged",
        "sourceCorrectness": "NOT_ASSESSED",
        "receipt": receipt.to_dict(),
        "freshctxObservationId": observation.id,
    }


def run_scenario() -> dict[str, object]:
    return {
        "scenario": "experimental_selection_provenance",
        "boundary": (
            "selection provenance is recorded separately from FreshCtx source freshness"
        ),
        "results": {
            "exact_filename": run_path("exact_filename"),
            "discovery": run_path("discovery"),
        },
    }


if __name__ == "__main__":
    outcome = run_scenario()
    assert outcome["results"]["exact_filename"]["freshnessStatus"] == FreshnessStatus.CURRENT.value
    assert outcome["results"]["discovery"]["freshnessStatus"] == FreshnessStatus.CURRENT.value
    print(json.dumps(outcome, indent=2, sort_keys=True))
