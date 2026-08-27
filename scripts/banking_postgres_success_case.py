"""Live disposable-Postgres acceptance test for a protected supplier wire."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from freshctx import FreshnessBlocked, FreshnessState, MemoryStore, guard, observe, reasoning


def run(dsn: str) -> dict[str, object]:
    import psycopg

    executed: list[str] = []
    query = """
        SELECT account_status, legal_hold, available_balance,
               beneficiary_status, risk_decision, treasury_approval,
               controller_approval
        FROM freshctx_wire_case WHERE wire_id = %s
    """
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS freshctx_wire_case")
            cursor.execute(
                """CREATE TABLE freshctx_wire_case (
                    wire_id text PRIMARY KEY, account_status text NOT NULL,
                    legal_hold boolean NOT NULL, available_balance numeric NOT NULL,
                    beneficiary_status text NOT NULL, risk_decision text NOT NULL,
                    treasury_approval text NOT NULL, controller_approval text NOT NULL
                )"""
            )
            cursor.execute(
                """INSERT INTO freshctx_wire_case VALUES
                    (%s, 'active', false, 812450.00, 'verified', 'allow', 'approved', 'approved')""",
                ("WIRE-2026-10419",),
            )

        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            store = MemoryStore()
            with guard(store=store, audit_path=audit_path):
                token = observe(
                    dsn,
                    adapter="postgres",
                    query=query,
                    params=["WIRE-2026-10419"],
                    ordered=True,
                )
                with reasoning("approve-$240000-supplier-wire", [token]) as decision:
                    pass

            with conn.cursor() as cursor:
                cursor.execute(
                    """UPDATE freshctx_wire_case
                       SET account_status = 'frozen', legal_hold = true
                       WHERE wire_id = %s""",
                    ("WIRE-2026-10419",),
                )

            with guard(policy="allow", store=store, audit_path=audit_path) as ctx:
                source_state = ctx.check(token).state
                decision_state = ctx.check(decision).state

            blocked = False
            try:
                with guard(store=store, audit_path=audit_path) as ctx:
                    ctx.run(lambda: executed.append("wire released"), depends_on=[decision])
            except FreshnessBlocked:
                blocked = True

            with audit_path.open(encoding="utf-8") as audit_file:
                event_count = sum(1 for _ in audit_file)

        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE freshctx_wire_case")

    passed = (
        source_state is FreshnessState.STALE_SOURCE
        and decision_state is FreshnessState.STALE_REASONING
        and blocked
        and not executed
    )
    return {
        "schema_version": 1,
        "case_id": "banking-payment-release-live-postgres",
        "method": "live disposable Postgres integration acceptance test",
        "transaction": "$240,000 supplier wire",
        "intervening_change": "source account frozen and placed on legal hold",
        "source_state": source_state.value,
        "decision_state": decision_state.value,
        "action_blocked": blocked,
        "action_executed": bool(executed),
        "audit_event_count": event_count,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("FRESHCTX_TEST_ADMIN_DSN"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.dsn:
        parser.error("provide --dsn or FRESHCTX_TEST_ADMIN_DSN")
    result = run(args.dsn)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(encoded, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
