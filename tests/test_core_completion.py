from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from freshctx import (
    FreshnessBlocked,
    FreshnessState,
    MemoryStore,
    SCHEMA_VERSION,
    SQLiteStore,
    StorageCorruptionError,
    StorageMigrationError,
    ValidationReport,
    adapter_contract_issues,
    guard,
    observe,
    reasoning,
    register_adapter,
)
from freshctx.adapters import ADAPTERS
from freshctx.model import AdapterResult, ObservationToken


class CoreCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audit = self.root / "audit.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_v01_store_is_migrated_without_data_loss(self):
        path = self.root / "legacy.db"
        token = ObservationToken("filesystem", "/tmp/source", "abc", id="legacy")
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO objects VALUES (?, ?, ?)",
            (token.id, "observation", json.dumps(token.__dict__, sort_keys=True)),
        )
        connection.commit()
        connection.close()
        store = SQLiteStore(path)
        self.addCleanup(store.close)
        self.assertEqual(store.schema_version, SCHEMA_VERSION)
        self.assertEqual(store.get(token.id), token)
        self.assertTrue(store.integrity_check())

    def test_future_store_schema_is_rejected(self):
        path = self.root / "future.db"
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE freshctx_schema (singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO freshctx_schema VALUES (1, 999)")
        connection.commit()
        connection.close()
        with self.assertRaises(StorageMigrationError):
            SQLiteStore(path)

    def test_corrupt_store_is_reported(self):
        path = self.root / "corrupt.db"
        path.write_bytes(b"not a sqlite database")
        with self.assertRaises(StorageCorruptionError):
            SQLiteStore(path)

    def test_all_builtin_adapters_satisfy_structural_contract(self):
        self.assertEqual(
            {name: adapter_contract_issues(adapter) for name, adapter in ADAPTERS.items()},
            {name: () for name in ADAPTERS},
        )

    def test_invalid_adapter_outcome_fails_closed(self):
        class InvalidAdapter:
            name = "invalid-contract"
            thread_safe = True

            def observe(self, locator, **_options):
                return ObservationToken(self.name, str(locator), "snapshot")

            def validate(self, _token):
                return AdapterResult("probably-current")

        register_adapter(InvalidAdapter.name, InvalidAdapter())
        store = MemoryStore()
        with guard(store=store, audit_path=self.audit):
            token = observe("value", adapter=InvalidAdapter.name)
        with guard(policy="allow", store=store, audit_path=self.audit) as ctx:
            result = ctx.check(token)
        self.assertEqual(result.state, FreshnessState.UNVERIFIABLE)
        self.assertEqual(result.adapter_results[0]["error_code"], "invalid_adapter_outcome")

    def test_async_check_and_action_preserve_blocking_boundary(self):
        async def scenario():
            source = self.root / "approval.txt"
            source.write_text("approved", encoding="utf-8")
            store = MemoryStore()
            async with guard(store=store, audit_path=self.audit):
                token = observe(source)
                with reasoning("approve", [token]) as decision:
                    pass
            source.write_text("revoked", encoding="utf-8")
            called = []
            async with guard(store=store, audit_path=self.audit) as ctx:
                result = await ctx.check_async(decision)
                self.assertEqual(result.state, FreshnessState.STALE_REASONING)
                with self.assertRaises(FreshnessBlocked):
                    await ctx.run_async(lambda: called.append(True), depends_on=[decision])
            self.assertEqual(called, [])

        asyncio.run(scenario())

    def test_async_current_action_can_be_awaited(self):
        async def scenario():
            source = self.root / "source.txt"
            source.write_text("current", encoding="utf-8")
            store = MemoryStore()
            async with guard(store=store, audit_path=self.audit):
                token = observe(source)
            async with guard(store=store, audit_path=self.audit) as ctx:
                value = await ctx.run_async(asyncio.sleep, 0, result="ran", depends_on=[token])
            self.assertEqual(value, "ran")

        asyncio.run(scenario())

    def test_large_graph_selectively_invalidates(self):
        store = MemoryStore()
        sources = []
        with guard(store=store, audit_path=self.audit):
            for index in range(128):
                path = self.root / f"source-{index}.txt"
                path.write_text(str(index), encoding="utf-8")
                sources.append((path, observe(path)))
            layer = [token for _, token in sources]
            while len(layer) > 1:
                next_layer = []
                for index in range(0, len(layer), 2):
                    with reasoning("aggregate", layer[index:index + 2]) as node:
                        pass
                    next_layer.append(node)
                layer = next_layer
            root = layer[0]
        sources[73][0].write_text("changed", encoding="utf-8")
        with guard(policy="allow", store=store, audit_path=self.audit, validation_workers=8) as ctx:
            result = ctx.check(root)
        self.assertEqual(result.state, FreshnessState.STALE_REASONING)
        self.assertEqual(len(result.adapter_results), 128)
        self.assertIn(sources[73][1].id, result.causes)

    def test_validation_report_serializes_to_schema_shape(self):
        report = ValidationReport(
            scenario="bounded payment change",
            freshctx_version="0.2.1",
            installation="pypi",
            environment={"python": "3.12"},
            expected="block",
            observed="block",
            verdict="pass",
            limitations=("synthetic source",),
            evidence=("audit.jsonl",),
        )
        value = report.to_dict()
        self.assertEqual(value["schema_version"], 1)
        self.assertEqual(value["limitations"], ["synthetic source"])

    def test_v01_synchronous_api_and_audit_contract_remain_compatible(self):
        source = self.root / "compatibility.txt"
        source.write_text("one", encoding="utf-8")
        store = MemoryStore()
        with guard(store=store, audit_path=self.audit) as ctx:
            token = observe(source)
            with reasoning("v01-decision", [token]) as decision:
                pass
            self.assertEqual(ctx.protect("unchanged", depends_on=[decision]), "unchanged")
        self.assertEqual(ctx.result.state, FreshnessState.CURRENT)
        events = [json.loads(line) for line in self.audit.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(events)
        self.assertEqual({event["schema_version"] for event in events}, {1})
        source.write_text("two", encoding="utf-8")
        calls = []
        with self.assertRaises(FreshnessBlocked):
            with guard(store=store, audit_path=self.audit) as action_ctx:
                action_ctx.run(lambda: calls.append(True), depends_on=[decision])
        self.assertEqual(calls, [])

    def test_cli_doctor_and_audit(self):
        store = self.root / "cli.db"
        doctor = subprocess.run(
            [sys.executable, "-m", "freshctx", "doctor", "--store", str(store)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertEqual(json.loads(doctor.stdout)["store_schema_version"], SCHEMA_VERSION)
        self.audit.write_text(json.dumps({"event_type": "observed"}) + "\n", encoding="utf-8")
        audit = subprocess.run(
            [sys.executable, "-m", "freshctx", "audit", "--audit", str(self.audit)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertEqual(json.loads(audit.stdout)["event_types"], {"observed": 1})


if __name__ == "__main__":
    unittest.main()
