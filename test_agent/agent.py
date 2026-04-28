"""
Demo ADK agent powered by adk-tools.

────────────────────────────────────────────────────────────────────
Quick start
────────────────────────────────────────────────────────────────────
1.  Install the package (editable, from repo root):

        pip install -e ".[all]"

2.  Copy the env template and fill in your keys:

        cp test_agent/.env.example test_agent/.env

3.  Load env vars and launch the ADK web UI:

        set -a && source test_agent/.env && set +a
        adk web test_agent

4.  Open http://127.0.0.1:8000 and start chatting.

────────────────────────────────────────────────────────────────────
How tools are loaded
────────────────────────────────────────────────────────────────────
``adk_tools`` scans the directory pointed to by ``ADK_TOOLS_DIR``
(set in .env) at import time and exposes every tool as a module-level
name.  The three lines below show all available import styles:

    # Style A — all tools at once (recommended for most agents)
    from adk_tools import discover_tools
    tools = discover_tools()

    # Style B — pick individual tools by name
    from adk_tools import score_function, get_weather_forecast
    tools = [score_function, get_weather_forecast]

    # Style C — load from a custom directory explicitly
    from adk_tools import load_tools
    tools = load_tools("/path/to/my/tools")

This file uses Style A.  Scroll to the bottom to switch styles.

────────────────────────────────────────────────────────────────────
Adding your own tools
────────────────────────────────────────────────────────────────────
Option 1 — YAML + logic.py in tools/:
    Create tools/<my_tool>/tool.yaml and tools/<my_tool>/logic.py.
    The tool appears automatically on next startup.

Option 2 — @function_tool decorator:
    # my_tools.py  (anywhere in your project)
    from adk_tools import function_tool
    from google.adk.tools.tool_context import ToolContext

    @function_tool
    async def greet_user(name: str, tool_context: ToolContext) -> str:
        \"\"\"Greet a user.\"\"\"
        return f"Hello {name}!"

    # agent.py — import the module so decorators register, then call discover_tools()
    import my_tools
    from adk_tools import discover_tools
    tools = discover_tools()   # includes greet_user
"""

from __future__ import annotations

import os
import sys

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if not os.environ.get("GOOGLE_API_KEY") and \
   not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    print(
        "ERROR: GOOGLE_API_KEY (or GOOGLE_APPLICATION_CREDENTIALS) is not set.\n"
        "       Copy test_agent/.env.example → test_agent/.env and fill in your key.",
        file=sys.stderr,
    )
    # Don't sys.exit — allow `adk web` to still serve an error page.

# ── Tool imports ──────────────────────────────────────────────────────────────
#
# Style A (default): discover all tools from ADK_TOOLS_DIR at once.
# Switch to Style B to cherry-pick specific tools by name.
#
from adk_tools import discover_tools  # noqa: E402

# ── (Optional) register @function_tool functions ─────────────────────────────
# Uncomment and point at your extra-tools module.
# import my_tools   # noqa: F401 — import triggers @function_tool registrations

# ── Build the agent ───────────────────────────────────────────────────────────

def build_agent():
    """
    Construct and return the ``google.adk.agents.LlmAgent``.

    Swap ``discover_tools()`` for a list of specific tools if you want a focused
    agent::

        from adk_tools import score_function, get_weather_forecast
        tools = [score_function, get_weather_forecast]
    """
    from google.adk.agents import LlmAgent  # type: ignore[import]

    return LlmAgent(
        model=os.environ.get("AGENT_MODEL", "gemini-2.0-flash"),
        name="demo_agent",
        description=(
            "Demo agent powered by adk-tools. "
            "Has access to every tool registered in ADK_TOOLS_DIR."
        ),
        instruction=(
            "You are a helpful assistant. "
            "Use the available tools to answer user requests. "
            "Always tell the user which tool you called and summarise the result clearly."
        ),
        tools=discover_tools(),
    )


# ── ADK entrypoint ────────────────────────────────────────────────────────────
# ``adk web test_agent`` discovers this module-level variable automatically.
root_agent = build_agent()
