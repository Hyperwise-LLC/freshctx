from __future__ import annotations

import compileall
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "LICENSE", "NOTICE", "README.md", "SECURITY.md", "CONTRIBUTING.md",
    "ARCHITECTURE.md", "API.md", "BACKLOG.md", "PROJECT_STATUS.md",
    "pyproject.toml", ".github/workflows/ci.yml", ".github/workflows/release.yml",
]


def main() -> int:
    missing = [name for name in REQUIRED if not (ROOT / name).exists()]
    if missing:
        print("Missing release files:", ", ".join(missing), file=sys.stderr)
        return 1
    root_schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    packaged = ROOT / "src" / "freshctx" / "schemas"
    if len(root_schemas) != 4:
        print("Expected four root schema files", file=sys.stderr); return 1
    for schema in root_schemas:
        json.loads(schema.read_text())
        packaged_schema = packaged / schema.name
        if not packaged_schema.exists() or packaged_schema.read_bytes() != schema.read_bytes():
            print(f"Packaged schema differs: {schema.name}", file=sys.stderr); return 1
    if not compileall.compile_dir(ROOT / "src", quiet=1) or not compileall.compile_dir(ROOT / "tests", quiet=1):
        return 1
    command = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(command, cwd=ROOT, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
