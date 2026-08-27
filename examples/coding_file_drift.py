from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning

with TemporaryDirectory() as directory:
    source = Path(directory) / "config.py"
    source.write_text("LIMIT = 10\n")
    store = MemoryStore()
    with guard(store=store, audit_path=Path(directory) / "audit.jsonl"):
        token = observe(source)
        with reasoning("code_review", depends_on=[token]) as finding:
            pass
    source.write_text("LIMIT = 100\n")
    try:
        with guard(store=store, audit_path=Path(directory) / "audit.jsonl") as ctx:
            ctx.run(lambda: print("deploy"), depends_on=[finding])
    except FreshnessBlocked as error:
        print(error.result.state.value)
