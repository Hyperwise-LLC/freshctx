from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessStatus, MemoryStore, guard, observe, reasoning


def deploy(target: str) -> None:
    print(f"DEPLOYED to {target}")


with TemporaryDirectory() as directory:
    root = Path(directory)
    config = root / "deployment.env"
    audit = root / "freshctx-audit.jsonl"
    config.write_text("TARGET=staging\n", encoding="utf-8")

    with guard(policy="block", store=MemoryStore(), audit_path=audit) as ctx:
        source = observe(config)
        with reasoning("choose_target", depends_on=[source]) as decision:
            target = "staging"
        ctx.run(deploy, target, depends_on=[decision])

    assert ctx.result is not None
    assert ctx.result.state is FreshnessStatus.CURRENT
    print(f"FreshCtx state: {ctx.result.state.value}")
    print(f"Audit events: {sum(1 for _ in audit.open(encoding='utf-8'))}")
