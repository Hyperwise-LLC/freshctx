from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from . import FreshnessBlocked, MemoryStore, __version__, guard, observe, reasoning


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


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m freshctx")
    parser.add_argument("command", nargs="?", choices=("demo", "version"), default="demo")
    args = parser.parse_args()
    if args.command == "version":
        print(__version__)
        return 0
    return demo()


if __name__ == "__main__":
    raise SystemExit(main())
