"""
agent_tools
===========

Proto-first, config-driven tool framework for ADK agents.

On first import every tool in ``AGENT_TOOLS_DIR`` is loaded, config-validated,
and exposed as a top-level name::

    from agent_tools import check_billing

    result  = await check_billing(customer_id="CUST-001", period="2026-04")
    schemas = check_billing.all_schemas()   # runtime is implicit — no extra import
    tools   = check_billing.all_tools()

Custom tool types can be registered *before* this module is imported::

    import agent_tools.core.type_registry as tr
    from my_package import MyHandler
    tr.default_type_registry.register("my_type", schema_path, MyHandler)
    import agent_tools                       # picks up the new type
"""

from __future__ import annotations

from agent_tools.core.context import current_request_headers, with_request_headers
from agent_tools.core.function import ToolFunction
from agent_tools.core.runtime import ToolRuntime
from agent_tools.core.tool_context import ToolContext

# ── Single shared runtime — loaded once at startup ────────────────────────────
runtime = ToolRuntime.from_env()

# ── Expose every registered tool as a module-level callable ──────────────────
_tool_functions: dict[str, ToolFunction] = {}
for _name in runtime._registry.names:
    _fn = ToolFunction(_name, runtime)
    globals()[_name] = _fn
    _tool_functions[_name] = _fn

__all__: list[str] = [
    "runtime",
    "ToolContext",
    "with_request_headers",
    "current_request_headers",
] + list(_tool_functions.keys())
