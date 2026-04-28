"""
adk_tools — YAML-driven, config-validated tool loader for Google ADK agents.

Three ways to use tools
------------------------

1. **Individual import** — each tool discovered from ``ADK_TOOLS_DIR`` is
   exposed as a module-level name at package import time::

       from adk_tools import score_function, get_weather_forecast

       root_agent = LlmAgent(tools=[score_function, get_weather_forecast], ...)

2. **All tools at once** — grab every discovered + decorated tool in one call::

       from adk_tools import discover_tools   # canonical name
       # from adk_tools import all_tools      # alias — same thing

       root_agent = LlmAgent(tools=discover_tools(), ...)

3. **``@function_tool`` decorator** — register inline functions anywhere and
   they are automatically merged into ``discover_tools()``::

       from adk_tools import function_tool
       from google.adk.tools.tool_context import ToolContext

       @function_tool
       async def greet_user(name: str, tool_context: ToolContext) -> str:
           \"\"\"Greet a user by name.\"\"\"
           return f"Hello {name}! session={tool_context.state.get('session_id')}"

Auto-discovery at import time
------------------------------
On first ``import adk_tools`` the package scans ``ADK_TOOLS_DIR``
(default: ``./tools`` relative to CWD) for OpenAPI and Function tools and
exposes each one as a module-level name.  MCP tools are skipped here because
their connection handshake is async — use :func:`load_tools_async` for those.

Set ``ADK_TOOLS_DIR`` to point at your tools directory::

    export ADK_TOOLS_DIR=/path/to/my/tools

Then any of these work::

    from adk_tools import my_tool_name          # direct name import
    import adk_tools; adk_tools.my_tool_name    # attribute access
    from adk_tools import all_tools             # full list

Mixing YAML tools + decorator tools
-------------------------------------
Both sources are merged in :func:`discover_tools`.  Import order matters for the
decorator — the module containing ``@function_tool`` functions must be imported
before ``discover_tools()`` is called::

    import my_custom_tools       # registers @function_tool functions
    tools = discover_tools()     # YAML tools + @function_tool tools

Async / MCP
-----------
::

    tools, exit_stack = await load_tools_async()
    async with exit_stack:
        root_agent = LlmAgent(tools=tools, ...)

Exported symbols
----------------
Auto-loaded tool names are added to this namespace dynamically at startup.
Fixed symbols:

- ``discover_tools``     — all discovered + registered tools as a list (canonical)
- ``all_tools``          — alias for ``discover_tools``
- ``function_tool``      — decorator: wrap & register a function as an ADK tool
- ``registered_tools``   — list of ``@function_tool``-registered tools only
- ``load_tools``         — explicit sync loader (custom dir / fine-grained control)
- ``load_tools_async``   — explicit async loader (includes MCP)
- ``ToolLoader``         — the underlying class for advanced usage
- ``TOOLS_DIR``          — resolved tools directory used for auto-discovery
"""

from __future__ import annotations

import logging
import os
import warnings
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable

from .loader import ToolLoader

log = logging.getLogger(__name__)

# ── Module-level loader singleton ─────────────────────────────────────────────
_loader = ToolLoader()

# ── @function_tool registry ───────────────────────────────────────────────────
# Populated by @function_tool decorators at module-import time.
_FUNCTION_REGISTRY: list[Any] = []

# ── Auto-discovered YAML tools ────────────────────────────────────────────────
# Loaded from ADK_TOOLS_DIR at package import time (sync; MCP skipped).
# Each tool is also injected into globals() so it can be imported by name.
_YAML_TOOLS: list[Any] = []

#: The tools directory resolved at import time.  Inspect this to see which
#: directory was scanned.  ``None`` if the directory did not exist.
TOOLS_DIR: Path | None = None

_env_dir = os.environ.get("ADK_TOOLS_DIR", "tools")
_candidate = Path(_env_dir)

if _candidate.is_dir():
    TOOLS_DIR = _candidate
    try:
        # Suppress the "MCP tools require load_async" warning during auto-load;
        # we'll emit a cleaner combined message below if needed.
        with warnings.catch_warnings(record=True) as _caught:
            warnings.simplefilter("always")
            _YAML_TOOLS = _loader.load_sync(_candidate)

        # Expose every tool as a module-level name for direct import.
        for _t in _YAML_TOOLS:
            _tname: str | None = getattr(_t, "name", None)
            if _tname and _tname.isidentifier():
                globals()[_tname] = _t
                log.debug("adk_tools: auto-loaded '%s' from %s", _tname, _candidate)

        if _caught:
            log.debug(
                "adk_tools: %d MCP tool(s) in '%s' skipped during sync load "
                "— call load_tools_async() to include them",
                len(_caught),
                _candidate,
            )
    except Exception as _exc:  # noqa: BLE001
        warnings.warn(
            f"adk_tools: failed to auto-load tools from '{_candidate}': {_exc}",
            stacklevel=2,
        )
else:
    log.debug(
        "adk_tools: tools directory '%s' not found — skipping auto-discovery. "
        "Set ADK_TOOLS_DIR or call load_tools(path) explicitly.",
        _candidate,
    )

# ── Public API ─────────────────────────────────────────────────────────────────


def discover_tools() -> list[Any]:
    """
    Return every available tool as a flat list ready for ``LlmAgent(tools=...)``.

    This is the primary way to get all tools in your agent — the same pattern
    used across the framework::

        from adk_tools import discover_tools

        tools = discover_tools()
        root_agent = LlmAgent(model="gemini-2.0-flash", tools=tools, ...)

    Combines:

    - YAML-configured tools auto-loaded from ``ADK_TOOLS_DIR`` at startup
    - All tools registered via ``@function_tool`` decorators

    Import any module containing ``@function_tool`` functions **before** calling
    this so their decorators have run::

        import my_extra_tools        # registers @function_tool functions
        tools = discover_tools()     # includes YAML tools + my_extra_tools tools

    .. note::
        MCP tools are **not** included here because their connection handshake
        is async.  Use :func:`load_tools_async` if you have MCP tools.
    """
    seen: set[int] = set()
    result: list[Any] = []
    for t in _YAML_TOOLS + _FUNCTION_REGISTRY:
        if id(t) not in seen:
            seen.add(id(t))
            result.append(t)
    return result


#: Alias for :func:`discover_tools` — use whichever name you prefer.
all_tools = discover_tools


def function_tool(func: Callable) -> Any:
    """
    Decorator — wrap *func* in ``google.adk.tools.FunctionTool`` and register
    it so :func:`all_tools` picks it up automatically.

    Works with both ``async def`` and plain ``def`` functions.  ADK derives the
    LLM tool schema from the function's signature + docstring.

    ``tool_context`` injection
    ~~~~~~~~~~~~~~~~~~~~~~~~~~
    Declare a parameter named ``tool_context`` typed as
    ``google.adk.tools.tool_context.ToolContext`` and ADK will inject the live
    session context.  It never appears in the LLM schema::

        from adk_tools import function_tool
        from google.adk.tools.tool_context import ToolContext

        @function_tool
        async def lookup_order(order_id: str, tool_context: ToolContext) -> dict:
            \"\"\"Look up an order by ID.\"\"\"
            uid = tool_context.state.get("user_id", "anon")
            ...

    The decorated name becomes the ``FunctionTool`` instance in the module
    namespace.  The original callable is accessible via ``my_func.func``.
    """
    try:
        from google.adk.tools import FunctionTool  # type: ignore[import]
        tool: Any = FunctionTool(func=func)
    except ImportError:
        # google-adk not installed (CI / test env without the package).
        # Store the raw function; it will be treated as-is by load_tools.
        tool = func

    _FUNCTION_REGISTRY.append(tool)
    return tool


def registered_tools() -> list[Any]:
    """
    Return a copy of all tools registered via ``@function_tool``.

    The module containing the decorated functions must be imported first::

        import my_tools          # runs @function_tool decorators
        tools = registered_tools()
    """
    return list(_FUNCTION_REGISTRY)


def load_tools(
    tools_dir: str | Path | None = None,
    *,
    include_registered: bool = True,
) -> list[Any]:
    """
    Explicitly load OpenAPI + Function tools from *tools_dir* (sync).

    Use this when you need a **custom directory** or want fine-grained control.
    For the common case — using ``ADK_TOOLS_DIR`` — just call :func:`all_tools`.

    MCP tools in *tools_dir* are skipped with a warning.  Use
    :func:`load_tools_async` to include them.

    :param tools_dir: Directory to scan.  Defaults to :data:`TOOLS_DIR` if
        auto-discovery resolved a directory, otherwise raises.
    :param include_registered: When ``True`` (default), append all
        ``@function_tool`` tools to the result.
    :returns: List of native ADK tool objects.
    """
    resolved = _resolve_dir(tools_dir)
    tools = _loader.load_sync(resolved)
    if include_registered:
        tools.extend(_FUNCTION_REGISTRY)
    return tools


async def load_tools_async(
    tools_dir: str | Path | None = None,
    *,
    include_registered: bool = True,
) -> tuple[list[Any], AsyncExitStack]:
    """
    Load **all** tool types (OpenAPI, MCP, Function) asynchronously.

    Required for MCP tools — their SSE / stdio connection is opened here.
    Keep the returned ``exit_stack`` alive for the lifetime of the agent
    session to hold MCP connections open::

        tools, exit_stack = await load_tools_async()
        async with exit_stack:
            root_agent = LlmAgent(tools=tools, ...)
            runner = Runner(agent=root_agent, ...)
            ...   # exit_stack closes MCP connections when this block exits

    :param tools_dir: Directory to scan.  Defaults to :data:`TOOLS_DIR`.
    :param include_registered: When ``True`` (default), append
        ``@function_tool`` tools.
    :returns: ``(tools, exit_stack)``.
    """
    resolved = _resolve_dir(tools_dir)
    tools, exit_stack = await _loader.load_async(resolved)
    if include_registered:
        tools.extend(_FUNCTION_REGISTRY)
    return tools, exit_stack


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_dir(tools_dir: str | Path | None) -> Path:
    if tools_dir is not None:
        return Path(tools_dir)
    if TOOLS_DIR is not None:
        return TOOLS_DIR
    raise FileNotFoundError(
        "No tools directory found. Either set the ADK_TOOLS_DIR environment "
        "variable, pass tools_dir= explicitly, or ensure a 'tools/' folder "
        "exists in the current working directory."
    )


# ── __all__ — fixed symbols + dynamically discovered tool names ───────────────

__all__: list[str] = [
    "TOOLS_DIR",
    "discover_tools",
    "all_tools",
    "function_tool",
    "registered_tools",
    "load_tools",
    "load_tools_async",
    "ToolLoader",
]
# Append auto-loaded tool names so `from adk_tools import *` works too.
__all__ += [
    getattr(t, "name")
    for t in _YAML_TOOLS
    if getattr(t, "name", None) and str(getattr(t, "name")).isidentifier()
]
