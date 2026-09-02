"""Run the bounded FreshCtx MCP Guard demo as a real stdio subprocess."""

from __future__ import annotations

import os

from mcp_balance_guard import build_demo_server


def main() -> None:
    scenario = os.environ.get("FRESHCTX_MCP_DEMO_SCENARIO", "stale")
    server, temporary_directory, _ = build_demo_server(scenario)
    try:
        server.run("stdio")
    finally:
        temporary_directory.cleanup()


if __name__ == "__main__":
    main()
