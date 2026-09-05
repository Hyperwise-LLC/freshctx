"""Agent-driven file discovery with observed reads and pre-action enforcement.

The default runner uses the OpenAI Agents SDK's model-free ScriptedModel for
repeatable verification. Pass ``--live`` to let a configured OpenAI model make
the discovery decision through the same list/read tool boundary.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from agents import Agent, Runner, function_tool
from agents.testing import ScriptedModel, assistant_message, function_call

from freshctx import MemoryStore, ObservedReadCapture, ProvenanceBlocked, ProvenanceBoundary, guard, observe


REQUEST = "Find the authoritative 2026 operations ledger and prepare the report."


def _scripted_model(read_source: str, selected_source: str, cited_source: str) -> ScriptedModel:
    final = json.dumps({"selectedSource": selected_source, "citedSources": [cited_source]})
    return ScriptedModel(
        [
            [function_call("list_sources", {}, call_id="list-sources")],
            [function_call("read_source", {"source": read_source}, call_id="read-source")],
            [assistant_message(final)],
        ]
    )


def run_case(case: str = "decoy", *, live: bool = False) -> dict[str, object]:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        authoritative = "authoritative_ledger_2026.csv"
        decoy = "2026_operations_ledger_FINAL.csv"
        (root / authoritative).write_text("account,total\nA,100\n", encoding="utf-8")
        (root / decoy).write_text("account,total\nA,80\n", encoding="utf-8")
        candidates = tuple(sorted((authoritative, decoy)))
        capture = ObservedReadCapture(root)

        @function_tool
        def list_sources() -> list[str]:
            """List the available ledger filenames."""
            return list(candidates)

        @function_tool
        def read_source(source: str) -> str:
            """Read one available ledger through the observed-access hook."""
            return capture.read_text(source)

        if live:
            model = os.environ.get("FRESHCTX_AGENT_MODEL", "gpt-5-mini")
        elif case == "consistent":
            model = _scripted_model(authoritative, authoritative, authoritative)
        elif case == "wrong_citation":
            model = _scripted_model(authoritative, authoritative, decoy)
        else:
            model = _scripted_model(decoy, decoy, decoy)

        instructions = (
            "Use the tools to inspect sources. Return only JSON with selectedSource "
            "and citedSources. Do not claim that a file was inspected unless you read it."
        )
        result = Runner.run_sync(
            Agent(name="source-discovery", instructions=instructions, model=model, tools=[list_sources, read_source]),
            REQUEST,
        )
        selection = json.loads(str(result.final_output))
        selected = selection["selectedSource"]
        cited = tuple(selection["citedSources"])

        store = MemoryStore()
        with guard(store=store):
            source = observe(root / selected)
        executions: list[str] = []
        provenance = ProvenanceBoundary(capture)
        try:
            with guard(store=store) as ctx:
                provenance.invoke(
                    ctx,
                    lambda: executions.append("report_prepared"),
                    depends_on=[source],
                    candidate_sources=candidates,
                    selected_source=selected,
                    cited_sources=cited,
                    required_sources=(authoritative,),
                    boundary="report_generation",
                )
        except ProvenanceBlocked:
            pass

        return {
            "case": case,
            "freshness": provenance.last_receipt.freshness_state.value,
            "provenance": provenance.last_receipt.provenance_assessment.value,
            "action": provenance.last_enforcement.boundary_outcome,
            "inspectedSources": list(provenance.last_receipt.inspected_sources),
            "selectedSource": selected,
            "citedSources": list(cited),
            "executions": executions,
            "receipt": provenance.last_receipt.to_dict(),
            "enforcement": provenance.last_enforcement.to_dict(),
        }


def run_demo() -> dict[str, object]:
    return {"cases": {case: run_case(case) for case in ("consistent", "decoy", "wrong_citation")}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="use a configured OpenAI model")
    args = parser.parse_args()
    output = run_case("live", live=True) if args.live else run_demo()
    print(json.dumps(output, indent=2, sort_keys=True))
