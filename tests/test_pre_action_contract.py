from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from freshctx import FreshnessBlocked, MemoryStore, guard, observe, reasoning
from freshctx.errors import ConfigurationError
from freshctx.integrations.pre_action import (
    EXPERIMENTAL_PRE_ACTION_CONTRACT,
    PreActionBoundary,
    PreActionCall,
)


class ExperimentalPreActionContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "state.txt"
        self.source.write_text("version=1\n", encoding="utf-8")
        self.store = MemoryStore()
        self.audit = self.root / "audit.jsonl"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _decision(self):
        with guard(store=self.store, audit_path=self.audit):
            token = observe(self.source)
            with reasoning("choose_action", depends_on=[token]) as decision:
                pass
        return decision

    def _boundary(self, decision):
        return PreActionBoundary(depends_on=[decision], store=self.store, audit_path=self.audit)

    def test_current_dependency_invokes_continuation_once(self):
        decision = self._decision()
        executed = []

        result = self._boundary(decision).invoke(
            PreActionCall(runtime="test-runtime", action="write", execution_id="run-123"),
            lambda value: executed.append(value) or value,
            "ok",
        )

        self.assertEqual(result, "ok")
        self.assertEqual(executed, ["ok"])

    def test_stale_dependency_blocks_before_continuation(self):
        decision = self._decision()
        executed = []
        self.source.write_text("version=2\n", encoding="utf-8")

        with self.assertRaises(FreshnessBlocked) as raised:
            self._boundary(decision).invoke(
                PreActionCall(runtime="test-runtime", action="write"),
                lambda: executed.append("called"),
            )

        self.assertEqual(executed, [])
        self.assertEqual(raised.exception.result.state.value, "STALE_REASONING")

    def test_async_boundary_awaits_continuation(self):
        async def scenario():
            decision = self._decision()
            executed = []

            async def continuation(value):
                executed.append(value)
                return value

            result = await self._boundary(decision).invoke_async(
                PreActionCall(runtime="test-runtime", action="async-write"),
                continuation,
                "ok",
            )
            return result, executed

        result, executed = asyncio.run(scenario())
        self.assertEqual(result, "ok")
        self.assertEqual(executed, ["ok"])

    def test_contract_metadata_is_persisted_without_arguments(self):
        decision = self._decision()
        call = PreActionCall(runtime="test-runtime", action="write", execution_id="run-123")
        self._boundary(decision).invoke(call, lambda secret: secret, "do-not-store")

        integration_nodes = [
            value
            for value in self.store.objects.values()
            if hasattr(value, "kind")
            if value.kind == "pre_action_integration"
        ]
        self.assertEqual(len(integration_nodes), 1)
        self.assertEqual(integration_nodes[0].metadata["contract"], EXPERIMENTAL_PRE_ACTION_CONTRACT)
        self.assertEqual(integration_nodes[0].metadata["runtime"], "test-runtime")
        self.assertEqual(integration_nodes[0].metadata["action"], "write")
        self.assertNotIn("do-not-store", repr(integration_nodes[0]))

    def test_invalid_configuration_is_rejected_early(self):
        with self.assertRaises(ConfigurationError):
            PreActionBoundary(depends_on=[], store=self.store)
        with self.assertRaises(ConfigurationError):
            PreActionBoundary(depends_on=["decision"], store=None)
        with self.assertRaises(ConfigurationError):
            PreActionCall(runtime="", action="write")
        with self.assertRaises(ConfigurationError):
            PreActionCall(runtime="runtime", action="")
        with self.assertRaises(ConfigurationError):
            PreActionCall(runtime="runtime", action="write", execution_id=123)  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            PreActionBoundary(depends_on="decision", store=self.store)


if __name__ == "__main__":
    unittest.main()
