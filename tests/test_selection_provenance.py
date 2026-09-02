import json
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from examples.selection_provenance.run import (
    AUTHORITATIVE_LEDGER,
    ROOT,
    run_scenario,
)


class SelectionProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema_path = ROOT / "selection-receipt.experimental.schema.json"
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )
        cls.outcome = run_scenario()

    def test_exact_filename_selects_and_opens_authoritative_ledger(self):
        result = self.outcome["results"]["exact_filename"]
        self.assertEqual(result["receipt"]["selectedSource"], AUTHORITATIVE_LEDGER)
        self.assertTrue(result["selectedSourceMatchesFixture"])
        self.assertTrue(result["realSourceOpened"])
        self.assertEqual(result["freshnessStatus"], "CURRENT")

    def test_discovery_selects_only_decoy_and_decoy_can_remain_current(self):
        result = self.outcome["results"]["discovery"]
        receipt = result["receipt"]
        self.assertNotEqual(receipt["selectedSource"], AUTHORITATIVE_LEDGER)
        self.assertEqual(receipt["inspectedSources"], [receipt["selectedSource"]])
        self.assertIn(AUTHORITATIVE_LEDGER, receipt["candidateSources"])
        self.assertFalse(result["selectedSourceMatchesFixture"])
        self.assertFalse(result["realSourceOpened"])
        self.assertEqual(result["freshnessStatus"], "CURRENT")
        self.assertEqual(result["sourceCorrectness"], "NOT_ASSESSED")
        self.assertEqual(receipt["sourceCorrectness"], "NOT_ASSESSED")

    def test_receipts_are_schema_valid_and_link_to_freshctx_observations(self):
        for result in self.outcome["results"].values():
            receipt = result["receipt"]
            self.validator.validate(receipt)
            self.assertTrue(receipt["observationId"])
            self.assertEqual(
                receipt["observationId"], result["freshctxObservationId"]
            )
            self.assertEqual(
                receipt["schemaVersion"],
                "freshctx.selection_receipt.experimental.v1",
            )

    def test_fixture_directory_contains_real_and_plausible_decoy(self):
        fixture_names = sorted(path.name for path in (ROOT / "fixtures").glob("*.csv"))
        self.assertEqual(
            fixture_names,
            ["2026_operations_ledger_FINAL.csv", AUTHORITATIVE_LEDGER],
        )


if __name__ == "__main__":
    unittest.main()
