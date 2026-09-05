import unittest

from examples.agent_source_provenance import run_demo


class AgentSourceProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_demo()["cases"]

    def test_sdk_agent_reads_authoritative_source_and_action_executes(self):
        result = self.results["consistent"]
        self.assertEqual(result["freshness"], "CURRENT")
        self.assertEqual(result["provenance"], "CONSISTENT")
        self.assertEqual(result["action"], "allowed")
        self.assertEqual(result["executions"], ["report_prepared"])

    def test_sdk_agent_reading_decoy_is_blocked_before_action(self):
        result = self.results["decoy"]
        self.assertEqual(result["freshness"], "CURRENT")
        self.assertEqual(result["provenance"], "INCONSISTENT")
        self.assertEqual(result["action"], "blocked")
        self.assertEqual(result["executions"], [])

    def test_right_read_wrong_citation_is_blocked(self):
        result = self.results["wrong_citation"]
        self.assertEqual(result["inspectedSources"], ["authoritative_ledger_2026.csv"])
        self.assertEqual(result["citedSources"], ["2026_operations_ledger_FINAL.csv"])
        self.assertEqual(result["freshness"], "CURRENT")
        self.assertEqual(result["provenance"], "INCONSISTENT")
        self.assertEqual(result["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
