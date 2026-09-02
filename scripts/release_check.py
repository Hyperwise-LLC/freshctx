from __future__ import annotations

import compileall
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "PyPI token": re.compile(r"pypi-[A-Za-z0-9_-]{40,}"),
    "GitHub token": re.compile(r"gh[oprsu]_[A-Za-z0-9]{30,}"),
    "Stripe secret key": re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}"),
}
REQUIRED = [
    "LICENSE", "NOTICE", "README.md", "SECURITY.md", "CONTRIBUTING.md",
    "ARCHITECTURE.md", "API.md", "BACKLOG.md", "PROJECT_STATUS.md", "SPEC.md",
    "TRADEMARKS.md", "GOVERNANCE.md", "RELEASING.md", "CODE_OF_CONDUCT.md",
    "SUPPORT.md", "THIRD_PARTY_NOTICES.md",
    "docs/ADAPTER_CONTRACT.md", "docs/SECURITY_MODEL.md", "docs/PERFORMANCE.md",
    "docs/FAQ.md", "docs/SUCCESS_CASES.md", "docs/CLI.md", "docs/INTEGRATIONS.md",
    "docs/MCP_GUARD.md", "docs/MCP_HOST_VALIDATION.md",
    "examples/mcp_balance_guard.py",
    "examples/mcp_guard_stdio_server.py", "examples/mcp_guard_external_host.py",
    "tests/test_mcp_guard_integration.py",
    "examples/selection_provenance/README.md",
    "examples/selection_provenance/run.py",
    "examples/selection_provenance/selection-receipt.experimental.schema.json",
    "examples/selection_provenance/fixtures/authoritative_ledger_2026.csv",
    "examples/selection_provenance/fixtures/2026_operations_ledger_FINAL.csv",
    "tests/test_selection_provenance.py",
    "docs/COMPATIBILITY_AUDIT.md", "docs/VALIDATION_REPORT.md",
    "docs/evidence/success-cases-v0.1.json",
    "docs/evidence/banking-postgres-v0.1.json",
    "docs/assets/freshctx-social-preview.png", "examples/quickstart.py",
    "examples/async_protected_action.py",
    "examples/langgraph_stale_config.py", "tests/test_langgraph_integration.py",
    "examples/agno_stale_tool.py", "tests/test_agno_integration.py",
    "examples/google_adk_stale_tool.py", "tests/test_google_adk_integration.py",
    "examples/stripe_subscription_drift.py", "tests/test_stripe_subscription_adapter.py",
    "examples/document_source_drift.py", "tests/test_document_source_drift.py",
    "examples/live_document_source_validation.py", "tests/test_live_document_source_validation.py",
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
    if len(root_schemas) != 6:
        print("Expected six root schema files", file=sys.stderr); return 1
    for schema in root_schemas:
        json.loads(schema.read_text())
        packaged_schema = packaged / schema.name
        if not packaged_schema.exists() or packaged_schema.read_bytes() != schema.read_bytes():
            print(f"Packaged schema differs: {schema.name}", file=sys.stderr); return 1
    forbidden = "Fresh" + "Bench"
    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and path.suffix.lower() not in {".docx", ".pyc"}:
            content = path.read_text(encoding="utf-8", errors="ignore")
            if forbidden in content:
                print(f"Forbidden project name in {path.relative_to(ROOT)}", file=sys.stderr); return 1
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(content):
                    print(f"Possible {label} in {path.relative_to(ROOT)}", file=sys.stderr); return 1
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
    langgraph = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "langgraph_stale_config.py")],
        cwd=ROOT,
        env=env,
    )
    if langgraph.returncode:
        return langgraph.returncode
    async_example = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "async_protected_action.py")],
        cwd=ROOT,
        env=env,
    )
    if async_example.returncode:
        return async_example.returncode
    return subprocess.run(
        [sys.executable, str(ROOT / "examples" / "real_world_success_cases.py")],
        cwd=ROOT,
        env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
