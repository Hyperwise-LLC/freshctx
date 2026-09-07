from __future__ import annotations

import asyncio
import json
import runpy
import tempfile
import unittest
import importlib.metadata
from dataclasses import replace
from pathlib import Path
from typing import Any

import jsonschema

from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import EventQueue

from freshctx import MemoryStore, guard, observe, reasoning
from freshctx.integrations.a2a import (
    A2A_EXTENSION_URI,
    A2ADelegation,
    FreshCtxA2AExecutor,
    MemoryDelegationReplayStore,
    SQLiteDelegationReplayStore,
    ValidationCircuitBreaker,
    a2a_delegation_metadata,
    attest_a2a_delegation,
)


KEY = b"freshctx-a2a-test-key-is-at-least-32-bytes"
ROOT = Path(__file__).resolve().parents[1]
try:
    MCP_V2 = int(importlib.metadata.version("mcp").split(".", 1)[0]) >= 2
except importlib.metadata.PackageNotFoundError:
    MCP_V2 = False


class Collector(EventQueue):
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


class Context:
    def __init__(self, metadata: dict[str, Any], task_id: str = "task-1") -> None:
        self.metadata = metadata
        self.task_id = task_id
        self.context_id = "context-1"


class RecordingExecutor(AgentExecutor):
    def __init__(self) -> None:
        self.executions = 0
        self.cancellations = 0

    async def execute(self, context: Any, event_queue: EventQueue) -> None:
        del context, event_queue
        self.executions += 1

    async def cancel(self, context: Any, event_queue: EventQueue) -> None:
        del context, event_queue
        self.cancellations += 1


class A2AIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "record.txt"
        self.source.write_text("state=ready\n", encoding="utf-8")
        self.store = MemoryStore()
        with guard(store=self.store, audit_path=self.root / "observe.jsonl"):
            token = observe(self.source)
            with reasoning("delegate", depends_on=[token]) as decision:
                pass
        self.token = token
        self.decision = decision

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _metadata(self, action_intent: Any = None, **changes: Any) -> dict[str, Any]:
        delegation = A2ADelegation.create(
            root_correlation_id="root-1",
            origin_agent="planner",
            receiving_agent="worker",
            skill_id="update_record",
            observation_ids=[self.token.id],
            ttl_seconds=60,
            parent_delegation_id="parent-1",
            action_intent=action_intent,
        )
        if changes:
            delegation = replace(delegation, **changes)
        attestation = attest_a2a_delegation(delegation, issuer="planner", key_id="key-1", key=KEY)
        return a2a_delegation_metadata(delegation, attestation)

    def _guard(self, executor: RecordingExecutor) -> FreshCtxA2AExecutor:
        return FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=[self.decision],
            store=self.store,
            key_resolver=lambda issuer, key_id: KEY if (issuer, key_id) == ("planner", "key-1") else None,
            audit_path=str(self.root / "a2a-audit.jsonl"),
        )

    def test_current_delegation_executes_receiver_once(self) -> None:
        executor = RecordingExecutor()
        guarded = self._guard(executor)
        queue = Collector()
        asyncio.run(guarded.execute(Context(self._metadata()), queue))
        self.assertEqual(executor.executions, 1)
        self.assertEqual(queue.events, [])
        self.assertEqual(guarded.last_delegation.parent_delegation_id, "parent-1")
        self.assertEqual(guarded.last_correlation.runtime, "a2a")

    def test_stale_evidence_rejects_before_receiver(self) -> None:
        executor = RecordingExecutor()
        guarded = self._guard(executor)
        self.source.write_text("state=changed\n", encoding="utf-8")
        queue = Collector()
        asyncio.run(guarded.execute(Context(self._metadata()), queue))
        self.assertEqual(executor.executions, 0)
        payload = dict(queue.events[0].metadata)[A2A_EXTENSION_URI]
        self.assertEqual(payload["reason"], "freshctx_blocked")
        self.assertEqual(payload["freshctx"]["state"], "STALE_REASONING")

    def test_missing_source_is_unverifiable_and_receiver_does_not_run(self) -> None:
        executor = RecordingExecutor()
        guarded = FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=["missing-dependency-id"],
            store=self.store,
            key_resolver=lambda issuer, key_id: KEY,
            audit_path=str(self.root / "a2a-audit.jsonl"),
        )
        queue = Collector()
        asyncio.run(guarded.execute(Context(self._metadata()), queue))
        self.assertEqual(executor.executions, 0)
        payload = dict(queue.events[0].metadata)[A2A_EXTENSION_URI]
        self.assertEqual(payload["freshctx"]["state"], "UNVERIFIABLE")

    def test_tampered_delegation_is_rejected_before_receiver(self) -> None:
        executor = RecordingExecutor()
        guarded = self._guard(executor)
        metadata = self._metadata()
        metadata[A2A_EXTENSION_URI]["delegation"]["skill_id"] = "transfer_funds"
        queue = Collector()
        asyncio.run(guarded.execute(Context(metadata), queue))
        self.assertEqual(executor.executions, 0)
        self.assertEqual(dict(queue.events[0].metadata)[A2A_EXTENSION_URI]["reason"], "payload_mismatch")

    def test_expired_delegation_is_rejected_before_receiver(self) -> None:
        executor = RecordingExecutor()
        guarded = self._guard(executor)
        metadata = self._metadata(created_at="2026-01-01T00:00:00+00:00", expires_at="2026-01-01T00:01:00+00:00")
        queue = Collector()
        asyncio.run(guarded.execute(Context(metadata), queue))
        self.assertEqual(executor.executions, 0)
        self.assertEqual(dict(queue.events[0].metadata)[A2A_EXTENSION_URI]["reason"], "expired")

    def test_missing_receipt_is_rejected_and_cancel_remains_framework_owned(self) -> None:
        executor = RecordingExecutor()
        guarded = self._guard(executor)
        queue = Collector()
        asyncio.run(guarded.execute(Context({}), queue))
        asyncio.run(guarded.cancel(Context({}), queue))
        self.assertEqual(executor.executions, 0)
        self.assertEqual(executor.cancellations, 1)
        self.assertEqual(dict(queue.events[0].metadata)[A2A_EXTENSION_URI]["reason"], "invalid_or_missing_delegation")

    def test_unrelated_change_does_not_block_declared_evidence(self) -> None:
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("v1\n", encoding="utf-8")
        unrelated.write_text("v2\n", encoding="utf-8")
        executor = RecordingExecutor()
        queue = Collector()
        asyncio.run(self._guard(executor).execute(Context(self._metadata()), queue))
        self.assertEqual(executor.executions, 1)

    def test_metadata_contains_no_business_payload_fields(self) -> None:
        serialized = repr(self._metadata())
        for forbidden in ("arguments", "credentials", "prompt", "source_content"):
            self.assertNotIn(forbidden, serialized)

    def test_action_intent_digest_matches_without_storing_arguments(self) -> None:
        intent = {"operation": "update_record", "record_id": "customer-7", "amount": 450}
        metadata = self._metadata(action_intent=intent)
        executor = RecordingExecutor()
        guarded = FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=[self.decision],
            store=self.store,
            key_resolver=lambda issuer, key_id: KEY,
            action_intent=lambda context: intent,
            audit_path=str(self.root / "intent-audit.jsonl"),
        )
        asyncio.run(guarded.execute(Context(metadata), Collector()))
        self.assertEqual(executor.executions, 1)
        delegation = metadata[A2A_EXTENSION_URI]["delegation"]
        self.assertEqual(set(delegation).intersection(intent), set())
        self.assertEqual(len(delegation["action_intent_digest"]), 64)

    def test_same_receipt_with_different_action_intent_is_rejected(self) -> None:
        metadata = self._metadata(action_intent={"operation": "update", "record_id": "7"})
        executor = RecordingExecutor()
        guarded = FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=[self.decision],
            store=self.store,
            key_resolver=lambda issuer, key_id: KEY,
            action_intent=lambda context: {"operation": "delete", "record_id": "7"},
        )
        queue = Collector()
        asyncio.run(guarded.execute(Context(metadata), queue))
        self.assertEqual(executor.executions, 0)
        self.assertEqual(dict(queue.events[0].metadata)[A2A_EXTENSION_URI]["reason"], "action_intent_mismatch")

    def test_legacy_receipt_shape_remains_valid(self) -> None:
        metadata = self._metadata()
        self.assertNotIn("action_intent_digest", metadata[A2A_EXTENSION_URI]["delegation"])
        executor = RecordingExecutor()
        queue = Collector()
        asyncio.run(self._guard(executor).execute(Context(metadata), queue))
        self.assertEqual(executor.executions, 1)

    def test_same_delegation_is_single_use(self) -> None:
        metadata = self._metadata()
        executor = RecordingExecutor()
        guarded = FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=[self.decision],
            store=self.store,
            key_resolver=lambda issuer, key_id: KEY,
            replay_store=MemoryDelegationReplayStore(),
        )
        first, second = Collector(), Collector()
        asyncio.run(guarded.execute(Context(metadata), first))
        asyncio.run(guarded.execute(Context(metadata), second))
        self.assertEqual(executor.executions, 1)
        self.assertEqual(dict(second.events[0].metadata)[A2A_EXTENSION_URI]["reason"], "delegation_replayed")

    def test_concurrent_replay_allows_exactly_one_execution(self) -> None:
        metadata = self._metadata()
        executor = RecordingExecutor()
        guarded = FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=[self.decision],
            store=self.store,
            key_resolver=lambda issuer, key_id: KEY,
            replay_store=MemoryDelegationReplayStore(),
        )
        queues = [Collector(), Collector()]

        async def run_both() -> None:
            await asyncio.gather(*(guarded.execute(Context(metadata), queue) for queue in queues))

        asyncio.run(run_both())
        self.assertEqual(executor.executions, 1)
        reasons = [dict(queue.events[0].metadata)[A2A_EXTENSION_URI]["reason"] for queue in queues if queue.events]
        self.assertEqual(reasons, ["delegation_replayed"])

    def test_sqlite_replay_store_is_shared_between_instances(self) -> None:
        path = str(self.root / "replay.sqlite3")
        metadata = self._metadata()
        delegation = A2ADelegation.from_dict(metadata[A2A_EXTENSION_URI]["delegation"])
        self.assertTrue(SQLiteDelegationReplayStore(path).consume(delegation.delegation_id, delegation.expires_at))
        self.assertFalse(SQLiteDelegationReplayStore(path).consume(delegation.delegation_id, delegation.expires_at))

    def test_unverifiable_validation_retries_within_attempt_bound(self) -> None:
        class FlakyStore:
            def __init__(self, wrapped: Any) -> None:
                self.wrapped = wrapped
                self.failed = False

            def get(self, object_id: str) -> Any:
                if not self.failed:
                    self.failed = True
                    return None
                return self.wrapped.get(object_id)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.wrapped, name)

        executor = RecordingExecutor()
        guarded = FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=[self.decision],
            store=FlakyStore(self.store),
            key_resolver=lambda issuer, key_id: KEY,
            validation_attempts=2,
        )
        queue = Collector()
        asyncio.run(guarded.execute(Context(self._metadata()), queue))
        self.assertEqual(executor.executions, 1)
        self.assertEqual(queue.events, [])

    def test_circuit_breaker_rejects_without_executing(self) -> None:
        breaker = ValidationCircuitBreaker(failure_threshold=1, open_seconds=60)
        breaker.record_unverifiable()
        executor = RecordingExecutor()
        guarded = FreshCtxA2AExecutor(
            executor,
            receiving_agent="worker",
            depends_on=[self.decision],
            store=self.store,
            key_resolver=lambda issuer, key_id: KEY,
            circuit_breaker=breaker,
        )
        queue = Collector()
        asyncio.run(guarded.execute(Context(self._metadata()), queue))
        self.assertEqual(executor.executions, 0)
        self.assertEqual(dict(queue.events[0].metadata)[A2A_EXTENSION_URI]["reason"], "validation_circuit_open")

    def test_public_delegation_schema_accepts_record(self) -> None:
        value = self._metadata()[A2A_EXTENSION_URI]["delegation"]
        schema = json.loads((ROOT / "schemas" / "a2a-delegation.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(value, schema, format_checker=jsonschema.FormatChecker())

    @unittest.skipUnless(MCP_V2, "official MCP Python SDK v2 is not installed")
    def test_three_agent_a2a_to_mcp_example(self) -> None:
        module = runpy.run_path(ROOT / "examples" / "a2a_to_mcp_delegation.py")
        current = asyncio.run(module["run_demo"]("current"))
        stale = asyncio.run(module["run_demo"]("stale"))
        unverifiable = asyncio.run(module["run_demo"]("unverifiable"))
        self.assertEqual(current["final_mcp_executions"], 1)
        self.assertEqual(stale["final_mcp_executions"], 0)
        self.assertEqual(unverifiable["final_mcp_executions"], 0)
        self.assertEqual(len(current["delegation_chain"]), 2)


if __name__ == "__main__":
    unittest.main()
