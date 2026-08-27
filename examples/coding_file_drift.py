from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, FreshnessStatus, MemoryStore, guard, observe, reasoning

with TemporaryDirectory() as directory:
    source = Path(directory) / "config.py"
    source.write_text("LIMIT = 10\n")
    store = MemoryStore()
    with guard(store=store, audit_path=Path(directory) / "audit.jsonl") as ctx:
        token = observe(source)
        with reasoning("code_review", depends_on=[token]) as finding:
            # Reality changes while the conclusion is being formed.
            source.write_text("LIMIT = 100\n")
        assert ctx.check(token).state is FreshnessStatus.STALE_SOURCE
    try:
        with guard(store=store, audit_path=Path(directory) / "audit.jsonl") as ctx:
            ctx.run(lambda: print("deploy"), depends_on=[finding])
    except FreshnessBlocked as error:
        assert error.result.state is FreshnessStatus.STALE_REASONING
        print(FreshnessStatus.STALE_SOURCE.value)
