"""Optional integrations for agent frameworks.

Framework dependencies remain optional. Public integration names are loaded
only when requested so importing a framework-neutral submodule does not require
Agno to be installed.
"""

from typing import Any


__all__ = ["FreshCtxAgnoBlocked", "agno_async_tool_hook", "agno_tool_hook"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .agno import FreshCtxAgnoBlocked, agno_async_tool_hook, agno_tool_hook

        values = {
            "FreshCtxAgnoBlocked": FreshCtxAgnoBlocked,
            "agno_async_tool_hook": agno_async_tool_hook,
            "agno_tool_hook": agno_tool_hook,
        }
        return values[name]
    raise AttributeError(name)
