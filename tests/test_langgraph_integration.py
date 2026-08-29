from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LangGraphIntegrationTests(unittest.TestCase):
    def test_stale_config_blocks_action_node(self):
        module = runpy.run_path(ROOT / "examples" / "langgraph_stale_config.py")
        self.assertTrue(module["run_demo"]())


if __name__ == "__main__":
    unittest.main()
