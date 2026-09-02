"""Bounded ElevenLabs voice-agent customer-record scenario.

No API key, microphone, or network call is required. The example invokes the
real ElevenLabs Python SDK client-tool registry used by a live Conversation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from elevenlabs.conversational_ai.conversation import ClientTools

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.elevenlabs import register_elevenlabs_client_tool


def _decision(store: MemoryStore, audit: Path, customer: Path, transcript: str | None):
    with guard(store=store, audit_path=audit):
        canonical = observe(customer)
        if transcript is None:
            dependencies: list[Any] = ["voice-match-unverifiable"]
        else:
            canonical_name = customer.read_text(encoding="utf-8").strip()
            # Exact matching is intentionally application-owned. A production
            # application may replace it with a reviewed semantic matcher.
            dependencies = [canonical] if transcript.strip() == canonical_name else ["voice-match-unverifiable"]
        with reasoning("confirm_voice_customer", depends_on=dependencies) as decision:
            pass
    return decision


async def _run_case(case: str) -> dict[str, Any]:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        customer = root / "customer-record.txt"
        audit = root / "voice-audit.jsonl"
        customer.write_text("Ada Lovelace\n", encoding="utf-8")
        store = MemoryStore()
        transcript = None if case == "unresolved_mismatch" else "Ada Lovelace"
        decision = _decision(store, audit, customer, transcript)
        if case == "record_changed":
            customer.write_text("Augusta Ada King\n", encoding="utf-8")

        executions: list[str] = []
        client_tools = ClientTools()

        def confirm_booking(parameters: dict[str, Any]) -> dict[str, str]:
            executions.append(parameters["booking_id"])
            return {"status": "confirmed"}

        register_elevenlabs_client_tool(
            client_tools,
            "confirm_booking",
            confirm_booking,
            depends_on=[decision],
            store=store,
            audit_path=audit,
        )
        response = await client_tools.handle(
            "confirm_booking",
            {"booking_id": "booking-sensitive-4471"},
        )
        return {"case": case, "response": response, "executions": executions}


def run_demo() -> list[dict[str, Any]]:
    results = [
        asyncio.run(_run_case(case))
        for case in ("current_match", "record_changed", "unresolved_mismatch")
    ]
    for result in results:
        response = result["response"]
        state = response.get("freshctx", {}).get("state", "CURRENT")
        print(f"{result['case']}: {response['status']} ({state}), executions={len(result['executions'])}")
    return results


if __name__ == "__main__":
    run_demo()
