"""Show why mutable evidence should expose a monotonic revision.

The business value returns to its original value, but its revision does not.
FreshCtx therefore detects the intervening change instead of treating the
value's return as proof that nothing happened.
"""

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, register_adapter
from freshctx.model import AdapterResult, ObservationToken


class VersionedRecordAdapter:
    name = "example_versioned_record"
    thread_safe = True

    def __init__(self, record: dict[str, object]) -> None:
        self.record = record

    def observe(self, locator: str) -> ObservationToken:
        revision = str(self.record["revision"])
        return ObservationToken(self.name, locator, revision, metadata={"freshness_strategy": "version"})

    def validate(self, token: ObservationToken) -> AdapterResult:
        revision = str(self.record["revision"])
        return AdapterResult(
            "equivalent" if revision == token.fingerprint else "changed",
            evidence={"observed_revision": token.fingerprint, "current_revision": revision},
        )


def run_demo() -> dict[str, object]:
    record: dict[str, object] = {"status": "approved", "revision": 1}
    adapter = VersionedRecordAdapter(record)
    register_adapter(adapter.name, adapter)
    store = MemoryStore()
    with guard(store=store, audit_path=".freshctx/aba-demo.jsonl"):
        token = observe("approval-7", adapter=adapter.name, freshness_strategy="version")

    record.update(status="revoked", revision=2)
    record.update(status="approved", revision=3)

    executed = 0
    try:
        with guard(store=store, audit_path=".freshctx/aba-demo.jsonl") as ctx:
            ctx.run(lambda: None, depends_on=[token], boundary="approval.commit")
            executed += 1
    except FreshnessBlocked as blocked:
        return {
            "value_returned_to_original": record["status"] == "approved",
            "observed_revision": 1,
            "current_revision": record["revision"],
            "freshness": blocked.result.state.value,
            "action_executions": executed,
        }
    raise AssertionError("the monotonic revision change should block the action")


if __name__ == "__main__":
    print(run_demo())
