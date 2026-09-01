import unittest

from examples.semantic_config_policy import run_scenario


class SemanticConfigPolicyTests(unittest.TestCase):
    def test_raw_and_selected_field_modes_have_explicit_boundaries(self):
        self.assertEqual(
            run_scenario(),
            {
                "raw_after_cosmetic_edit": "STALE_SOURCE",
                "selected_after_cosmetic_edit": "CURRENT",
                "selected_after_material_edit": "STALE_SOURCE",
                "invalid_document": "UNVERIFIABLE",
                "missing_declared_field": "UNVERIFIABLE",
            },
        )


if __name__ == "__main__":
    unittest.main()
