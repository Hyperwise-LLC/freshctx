import unittest

from freshctx import FreshnessState
from examples.real_world_success_cases import run_all


class RealWorldSuccessCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_all()

    def test_all_nine_domains_are_covered(self):
        self.assertEqual(len(self.results), 9)
        self.assertEqual(
            {result.domain for result in self.results},
            {
                "banking and payments",
                "e-commerce",
                "audit and assurance",
                "insurance",
                "healthcare operations",
                "enterprise procurement",
                "customer service",
                "IT and security operations",
                "legal and contract operations",
            },
        )

    def test_every_protected_action_is_blocked_before_execution(self):
        for result in self.results:
            with self.subTest(case=result.case_id):
                self.assertTrue(result.action_blocked)
                self.assertFalse(result.action_executed)
                self.assertGreater(result.audit_event_count, 0)

    def test_changed_or_unreachable_evidence_never_becomes_current(self):
        for result in self.results:
            with self.subTest(case=result.case_id):
                self.assertIn(
                    result.changed_source_state,
                    {FreshnessState.STALE_SOURCE.value, FreshnessState.UNVERIFIABLE.value},
                )
                self.assertIn(
                    result.decision_state,
                    {FreshnessState.STALE_REASONING.value, FreshnessState.UNVERIFIABLE.value},
                )

    def test_unaffected_evidence_remains_current(self):
        for result in self.results:
            with self.subTest(case=result.case_id):
                self.assertEqual(result.unaffected_source_state, FreshnessState.CURRENT.value)


if __name__ == "__main__":
    unittest.main()
