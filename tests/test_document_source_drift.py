import unittest

from examples.document_source_drift import run_scenario


class DocumentSourceDriftTests(unittest.TestCase):
    def test_only_claims_depending_on_changed_source_become_stale(self):
        self.assertEqual(
            run_scenario(),
            {
                "claim-treatment-timing": "STALE_REASONING",
                "claim-review-conclusion": "CURRENT",
                "claim-rebuttal-exists": "CURRENT",
                "claim-current-probe-status": "STALE_REASONING",
            },
        )


if __name__ == "__main__":
    unittest.main()
