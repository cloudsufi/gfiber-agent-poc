"""
Interactive ADK agent with all registered tools.

Serves a live Web UI via the ``adk web`` command. Every tool is discoverable
and callable via natural language prompts. Session state, tool context, and
structured logging flow through the framework seamlessly.

Quick Start
-----------
1. Export your API keys:

    export GOOGLE_API_KEY=<your-gemini-api-key>
    export WEATHER_API_KEY=demo-bearer-token
    export GFIBER_API_KEY=<optional-for-get_customer_details>
    export GFIBER_API_BASE_URL=<optional-api-server-url>

2. Start the web server:

    adk web test_agent

3. Open http://127.0.0.1:8000 in your browser and start chatting.

Tip: Use the provided .env.example template:

    cp test_agent/.env.example test_agent/.env
    # edit .env with real keys
    set -a && source test_agent/.env && set +a
    adk web test_agent
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agent_tools import ToolContext, discover_tools

_ALL_TOOL_FUNCTIONS = discover_tools()

# Fail fast if Gemini API key is not set — prevents cryptic ADK error later
if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    print(
        "ERROR: Set GOOGLE_API_KEY (or GOOGLE_APPLICATION_CREDENTIALS) before running.",
        file=sys.stderr,
    )


def build_agent():
    """Build a ``google.adk.agents.LlmAgent`` wired to every registered tool."""
    from google.adk.agents import LlmAgent

    tools = [AgentToolsAdapter(tf) for tf in _ALL_TOOL_FUNCTIONS]

    return LlmAgent(
        model="gemini-2.0-flash",
        name="demo_agent",
        description=(
            "Demo agent showcasing the ai-agent-shared-tools framework. "
            "Has access to every tool registered by the package at startup."
        ),
        instruction=(
            "You are a helpful assistant. Use the available tools to answer "
            "questions about customer billing and to enrich lead information. "
            "Always cite which tool you used."
        ),
        tools=tools,
    )


class AgentToolsAdapter:
    """
    Wraps a framework :class:`ToolFunction` so it satisfies the ADK
    :class:`~google.adk.tools.BaseTool` contract without pulling the ADK import
    into framework code.

    ``BaseTool`` is imported lazily so this module still loads on machines
    that don't have ``google-adk`` installed.
    """

    def __new__(cls, tool_fn):  # type: ignore[no-untyped-def]
        # Build the subclass lazily at first instantiation so BaseTool is only
        # imported when ADK is actually needed.
        from google.adk.tools import BaseTool
        from google.genai import types

        class _Adapter(BaseTool):
            def __init__(self, tf) -> None:
                super().__init__(
                    name=tf.schema["name"],
                    description=tf.schema.get("description", ""),
                )
                self._tool_fn = tf

            def _get_declaration(self):
                return types.FunctionDeclaration.model_validate(
                    {
                        "name": self._tool_fn.schema["name"],
                        "description": self._tool_fn.schema.get("description", ""),
                        "parameters": self._tool_fn.schema.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )

            async def run_async(self, *, args: dict[str, Any], tool_context) -> Any:
                # Bridge ADK's tool_context into framework's ToolContext
                uid = ""
                if tool_context and hasattr(tool_context, "state"):
                    uid = tool_context.state.get("user_id", "") if tool_context.state else ""
                hashed = hashlib.sha256(uid.encode()).hexdigest() if uid else ""

                session_id = ""
                if tool_context and hasattr(tool_context, "state"):
                    session_id = tool_context.state.get("session_id", str(uuid4())) if tool_context.state else str(uuid4())
                else:
                    session_id = str(uuid4())

                tc = ToolContext(
                    session_id=session_id,
                    hashed_user_id=hashed,
                    event_type=tool_context.state.get("event_type", "adk_tool_call") if (tool_context and hasattr(tool_context, "state") and tool_context.state) else "adk_tool_call",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                return await self._tool_fn(tc, **args)

        return _Adapter(tool_fn)


# ADK discovers this module-level variable when running `adk web test_agent`
root_agent = build_agent()
