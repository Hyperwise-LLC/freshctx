from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from . import SCHEMA_VERSION, FreshnessBlocked, MemoryStore, SQLiteStore, __version__, guard, observe, reasoning


def demo() -> int:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "approval.txt"
        audit = root / "freshctx-audit.jsonl"
        source.write_text("APPROVED", encoding="utf-8")
        store = MemoryStore()
        with guard(store=store, audit_path=audit):
            token = observe(source)
            with reasoning("approve_action", [token]) as decision:
                pass
        source.write_text("REVOKED", encoding="utf-8")
        try:
            with guard(store=store, audit_path=audit) as ctx:
                ctx.run(lambda: print("ACTION RAN"), depends_on=[decision])
        except FreshnessBlocked as exc:
            print(f"BLOCKED: {exc.result.state.value}")
            print(f"AUDIT EVENTS: {len(audit.read_text(encoding='utf-8').splitlines())}")
            return 0
    return 1


def check(store_path: Path, subject: str, audit_path: Path, policy: str) -> int:
    store = SQLiteStore(store_path)
    try:
        with guard(policy=policy, store=store, audit_path=audit_path) as ctx:
            result = ctx.check(subject)
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0 if result.state.value == "CURRENT" else 2
    finally:
        store.close()


def audit_summary(audit_path: Path) -> int:
    if not audit_path.exists():
        print(f"Audit file not found: {audit_path}", file=sys.stderr)
        return 2
    events = []
    line_number = 0
    try:
        for line_number, line in enumerate(audit_path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                events.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Invalid audit file near line {line_number}: {exc}", file=sys.stderr)
        return 2
    counts = Counter(str(event.get("event_type", "unknown")) for event in events)
    print(json.dumps({"events": len(events), "event_types": dict(sorted(counts.items()))}, indent=2))
    return 0


def doctor(store_path: Path | None) -> int:
    report = {
        "freshctx_version": __version__,
        "python": platform.python_version(),
        "supported_schema_version": SCHEMA_VERSION,
        "status": "ok",
    }
    store = None
    try:
        if store_path is not None:
            store = SQLiteStore(store_path)
            report["store"] = str(store_path)
            report["store_schema_version"] = store.schema_version
            report["store_integrity"] = store.integrity_check()
    except Exception as exc:
        report["status"] = "error"
        report["error"] = type(exc).__name__
    finally:
        if store is not None:
            store.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="freshctx")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("demo", help="run the installed-package stale-context demo")
    subparsers.add_parser("version", help="print the installed FreshCtx version")
    check_parser = subparsers.add_parser("check", help="check a stored subject immediately")
    check_parser.add_argument("subject")
    check_parser.add_argument("--store", type=Path, default=Path(".freshctx/freshctx.db"))
    check_parser.add_argument("--audit", type=Path, default=Path(".freshctx/audit.jsonl"))
    check_parser.add_argument("--policy", choices=("block", "warn", "allow"), default="block")
    audit_parser = subparsers.add_parser("audit", help="summarize a JSONL audit trail")
    audit_parser.add_argument("--audit", type=Path, default=Path(".freshctx/audit.jsonl"))
    doctor_parser = subparsers.add_parser("doctor", help="check the installation and optional store")
    doctor_parser.add_argument("--store", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "demo"
    if command == "version":
        print(__version__)
        return 0
    if command == "demo":
        return demo()
    if command == "check":
        return check(args.store, args.subject, args.audit, args.policy)
    if command == "audit":
        return audit_summary(args.audit)
    if command == "doctor":
        return doctor(args.store)
    parser.error(f"unsupported command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
