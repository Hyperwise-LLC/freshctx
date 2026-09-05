import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from examples.selection_provenance.run import AUTHORITATIVE_LEDGER, DECOY_LEDGER, run_scenario
from freshctx import MemoryStore, ObservedReadCapture, guard, observe

ROOT = Path(__file__).resolve().parents[1]


class ObservedEvidenceProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads((ROOT / "src/freshctx/schemas/observed-evidence-provenance.schema.json").read_text())
        cls.validator = Draft202012Validator(schema, format_checker=FormatChecker())
        cls.outcome = run_scenario()

    def test_exact_source_is_observed_and_consistent(self):
        result = self.outcome["results"]["exact_filename"]
        self.assertEqual(result["freshnessStatus"], "CURRENT")
        self.assertEqual(result["provenanceAssessment"], "CONSISTENT")
        self.assertEqual(result["receipt"]["inspected_sources"], [AUTHORITATIVE_LEDGER])

    def test_decoy_can_be_current_without_being_provenance_consistent(self):
        result = self.outcome["results"]["discovery_wrong_source"]
        self.assertEqual(result["freshnessStatus"], "CURRENT")
        self.assertEqual(result["provenanceAssessment"], "INCONSISTENT")
        self.assertIn("required_source_not_inspected", result["receipt"]["assessment_reasons"])

    def test_right_file_read_wrong_file_cited_is_detected_separately(self):
        result = self.outcome["results"]["right_read_wrong_citation"]
        receipt = result["receipt"]
        self.assertEqual(result["freshnessStatus"], "CURRENT")
        self.assertEqual(result["provenanceAssessment"], "INCONSISTENT")
        self.assertEqual(receipt["inspected_sources"], [AUTHORITATIVE_LEDGER])
        self.assertEqual(receipt["cited_sources"], [DECOY_LEDGER])
        self.assertIn("cited_source_not_inspected", receipt["assessment_reasons"])

    def test_receipts_validate_and_link_to_correlation_and_observation(self):
        for result in self.outcome["results"].values():
            receipt = result["receipt"]
            self.validator.validate(receipt)
            self.assertTrue(receipt["correlation_id"])
            self.assertEqual(len(receipt["observation_ids"]), 1)

    def test_inspected_sources_come_only_from_successful_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("safe", encoding="utf-8")
            capture = ObservedReadCapture(root)
            self.assertEqual(capture.read_text("one.txt"), "safe")
            with self.assertRaises(FileNotFoundError):
                capture.read_text("missing.txt")
            self.assertEqual(capture.inspected_sources, ("one.txt",))
            self.assertNotIn("safe", repr(capture.events))

    def test_read_hook_rejects_sources_outside_root(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = ObservedReadCapture(directory)
            with self.assertRaisesRegex(ValueError, "inside the configured read root"):
                capture.read_text(Path(directory).parent / "outside.txt")

    def test_no_policy_remains_not_assessed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "record.txt"
            source.write_text("record", encoding="utf-8")
            capture = ObservedReadCapture(root)
            capture.read_text(source)
            store = MemoryStore()
            with guard(store=store):
                observation = observe(source)
            with guard(policy="allow", store=store) as ctx:
                ctx.run(lambda: None, depends_on=[observation])
            receipt = capture.receipt(ctx.correlation, selected_source="record.txt")
            self.assertEqual(receipt.provenance_assessment.value, "NOT_ASSESSED")


if __name__ == "__main__":
    unittest.main()
