import json
import unittest
from dataclasses import asdict
from pathlib import Path

from freshctx.model import CheckResult, FreshnessState, ObservationToken, ReasoningNode


ROOT = Path(__file__).resolve().parents[1]


class SchemaFilesTests(unittest.TestCase):
    def test_all_schema_files_are_valid_json_with_required_identity(self):
        files = sorted((ROOT / "schemas").glob("*.schema.json"))
        self.assertEqual(len(files), 4)
        for path in files:
            schema = json.loads(path.read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("$id", schema)
            self.assertEqual(schema["type"], "object")

    def test_domain_objects_cover_schema_required_fields(self):
        token = ObservationToken("filesystem", "/tmp/example", "abc")
        node = ReasoningNode("example", (token.id,), "def")
        result = CheckResult(FreshnessState.CURRENT, node.id)
        samples = {
            "observation-token.schema.json": asdict(token),
            "reasoning-node.schema.json": asdict(node),
            "check-result.schema.json": result.to_dict(),
        }
        for filename, value in samples.items():
            schema = json.loads((ROOT / "schemas" / filename).read_text())
            self.assertTrue(set(schema["required"]).issubset(value))


if __name__ == "__main__":
    unittest.main()
