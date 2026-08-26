from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning


with TemporaryDirectory() as directory:
    config = Path(directory) / "config.yaml"
    config.write_text("target: staging\n")
    store = MemoryStore()

    with guard(store=store) as ctx:
        observed = observe(config)
        with reasoning("deployment_target", depends_on=[observed]) as decision:
            target = "staging"
        ctx.protect(target, depends_on=[decision])

    config.write_text("target: production\n")

    try:
        with guard(store=store) as ctx:
            ctx.protect(target, depends_on=[decision])
    except FreshnessBlocked as blocked:
        print(blocked.result.state.value)
        print(blocked.result.causes)
