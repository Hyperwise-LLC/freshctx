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
    "ARCHITECTURE.md", "API.md", "BACKLOG.md", "PROJECT_STATUS.md", "SPEC.md",
    "TRADEMARKS.md", "GOVERNANCE.md", "RELEASING.md", "CODE_OF_CONDUCT.md",
    "docs/ADAPTER_CONTRACT.md", "docs/SECURITY_MODEL.md", "docs/PERFORMANCE.md",
    "docs/FAQ.md", "docs/SUCCESS_CASES.md",
    "docs/evidence/success-cases-v0.1.json",
    "docs/evidence/banking-postgres-v0.1.json",
    "docs/assets/freshctx-social-preview.png", "examples/quickstart.py",
    "examples/real_world_success_cases.py", "tests/test_success_cases.py",
    "scripts/banking_postgres_success_case.py",
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
    forbidden = "Fresh" + "Bench"
    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and path.suffix.lower() not in {".docx", ".pyc"}:
            if forbidden in path.read_text(encoding="utf-8", errors="ignore"):
                print(f"Forbidden project name in {path.relative_to(ROOT)}", file=sys.stderr); return 1
    if not compileall.compile_dir(ROOT / "src", quiet=1) or not compileall.compile_dir(ROOT / "tests", quiet=1):
        return 1
    command = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode:
        return result.returncode
    quickstart = subprocess.run([sys.executable, str(ROOT / "examples" / "quickstart.py")], cwd=ROOT, env=env)
    if quickstart.returncode:
        return quickstart.returncode
    return subprocess.run(
        [sys.executable, str(ROOT / "examples" / "real_world_success_cases.py")],
        cwd=ROOT,
        env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
