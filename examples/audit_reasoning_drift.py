from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessStatus, MemoryStore, guard, observe, reasoning

with TemporaryDirectory() as directory:
    root = Path(directory); a = root / "a.txt"; b = root / "b.txt"
    a.write_text("a1"); b.write_text("b1"); store = MemoryStore(); audit = root / "audit.jsonl"
    with guard(store=store, audit_path=audit):
        ta, tb = observe(a), observe(b)
        with reasoning("finding-a", depends_on=[ta]) as finding_a: pass
        with reasoning("finding-b", depends_on=[tb]) as finding_b: pass
    a.write_text("a2")
    with guard(policy="allow", store=store, audit_path=audit) as ctx:
        assert ctx.check(finding_a).state is FreshnessStatus.STALE_REASONING
        assert ctx.check(finding_b).state is FreshnessStatus.CURRENT
    print("only finding-a invalidated")
