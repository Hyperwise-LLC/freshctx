import copy
import json
import tempfile
import unittest
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from freshctx import FreshnessState, MemoryStore, ValidationReport, guard, observe, reasoning
from freshctx.redaction import REDACTED


ROOT = Path(__file__).resolve().parents[1]


class SchemaConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "schemas").glob("*.schema.json"))
        }
        cls.validators = {
            name: Draft202012Validator(schema, format_checker=FormatChecker())
            for name, schema in cls.schemas.items()
        }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.source = self.root / "source.txt"; self.source.write_text("one", encoding="utf-8")
        self.audit = self.root / "audit.jsonl"; self.store = MemoryStore()
        with guard(store=self.store, audit_path=self.audit):
            self.token = observe(self.source)
            with reasoning("release-decision", [self.token], {"api_key": "sensitive", "policy": {"b": 2, "a": 1}}) as context:  # pragma: allowlist secret
                pass
        self.node = context.node

    def tearDown(self): self.tmp.cleanup()

    def validate(self, schema_name, value): self.validators[schema_name].validate(value)

    def test_all_schema_files_have_required_identity(self):
        self.assertEqual(len(self.schemas), 5)
        for schema in self.schemas.values():
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("$id", schema); self.assertEqual(schema["type"], "object")

    def test_runtime_observation_and_reasoning_conform(self):
        token = asdict(self.token); node = asdict(self.node); node["dependencies"] = list(node["dependencies"])
        self.validate("observation-token.schema.json", token)
        self.validate("reasoning-node.schema.json", node)
        self.assertEqual(node["metadata"]["api_key"], REDACTED)
        self.assertRegex(node["digest"], r"^[0-9a-f]{64}$")

    def test_runtime_check_results_cover_every_freshness_state(self):
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx:
            current = ctx.check(self.node); unverifiable = ctx.check("missing")
        self.source.write_text("changed", encoding="utf-8")
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx:
            stale_source = ctx.check(self.token); stale_reasoning = ctx.check(self.node)
        results = [current, stale_source, stale_reasoning, unverifiable]
        self.assertEqual({result.state for result in results}, set(FreshnessState))
        for result in results: self.validate("check-result.schema.json", result.to_dict())

    def test_runtime_audit_events_conform(self):
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx: ctx.check(self.node)
        events = [json.loads(line) for line in self.audit.read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(events), 4)
        for event in events: self.validate("audit-event.schema.json", event)

    def test_validation_report_conforms(self):
        report = ValidationReport(
            scenario="schema test",
            freshctx_version="0.2.1",
            installation="pypi",
            environment={"python": "3.12"},
            expected="block",
            observed="block",
            verdict="pass",
        )
        self.validate("validation-report.schema.json", report.to_dict())

    def test_negative_fixtures_reject_missing_wrong_and_additional_fields(self):
        token = asdict(self.token)
        missing = copy.deepcopy(token); missing.pop("id")
        wrong = copy.deepcopy(token); wrong["metadata"] = []
        additional = copy.deepcopy(token); additional["unexpected"] = True
        for invalid in (missing, wrong, additional):
            with self.assertRaises(ValidationError): self.validate("observation-token.schema.json", invalid)

    def test_negative_fixtures_reject_timestamps_digests_dependencies_and_states(self):
        node = asdict(self.node); node["dependencies"] = list(node["dependencies"])
        bad_time = copy.deepcopy(node); bad_time["created_at"] = "not-a-timestamp"
        bad_digest = copy.deepcopy(node); bad_digest["digest"] = "short"
        bad_dependencies = copy.deepcopy(node); bad_dependencies["dependencies"] = []
        with guard(policy="allow", store=self.store, audit_path=self.audit) as ctx: result = ctx.check(self.node).to_dict()
        bad_state = copy.deepcopy(result); bad_state["state"] = "UNKNOWN"
        for schema_name, invalid in (
            ("reasoning-node.schema.json", bad_time),
            ("reasoning-node.schema.json", bad_digest),
            ("reasoning-node.schema.json", bad_dependencies),
            ("check-result.schema.json", bad_state),
        ):
            with self.assertRaises(ValidationError): self.validate(schema_name, invalid)

    def test_packaged_schemas_match_root_contracts(self):
        packaged = files("freshctx").joinpath("schemas")
        self.assertEqual(set(self.schemas), {entry.name for entry in packaged.iterdir() if entry.name.endswith(".json")})
        for name, schema in self.schemas.items():
            self.assertEqual(schema, json.loads(packaged.joinpath(name).read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
