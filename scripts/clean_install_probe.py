"""Probe an installed FreshCtx distribution without importing from a checkout."""

from __future__ import annotations

import json
import platform
import sys
import tempfile
from importlib.metadata import distribution
from pathlib import Path

import freshctx
from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


def main():
    with tempfile.TemporaryDirectory(prefix="freshctx-pypi-probe-") as directory:
        root = Path(directory)
        source, audit = root / "evidence.json", root / "audit.jsonl"
        source.write_text('{"approval": true}\n')
        store = MemoryStore()
        with guard(store=store, audit_path=audit):
            token = observe(source)
            with reasoning("clean_install_probe", [token]) as node:
                pass
        source.write_text('{"approval": false}\n')
        try:
            with guard(store=store, audit_path=audit) as ctx:
                ctx.run(lambda: None, depends_on=[node])
        except FreshnessBlocked as blocked:
            result = blocked.result
        events = [json.loads(line) for line in audit.read_text().splitlines()]
        dist = distribution("freshctx")
        payload = {
            "python": platform.python_version(),
            "executable": sys.executable,
            "installed_version": dist.version,
            "module_path": str(Path(freshctx.__file__).resolve()),
            "distribution_path": str(Path(dist.locate_file("" )).resolve()),
            "state": result.state.value,
            "policy_decision": result.policy_decision,
            "action_allowed_events": sum(event["event_type"] == "action_allowed" for event in events),
            "policy_event": next(event for event in events if event["event_type"] == "policy_applied"),
        }
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
