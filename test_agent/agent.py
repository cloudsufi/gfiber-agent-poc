"""
Demo ADK agent that consumes tools from the ``agent_tools`` package.

The agent is built from every tool registered by ``agent_tools`` at import
time — no manual wiring. Each ``ToolFunction`` is wrapped in a thin
:class:`AgentToolsAdapter` so ADK can discover its JSON-Schema declaration
(derived from the tool's ``input.yaml``) and dispatch calls into the
framework runtime.

AgentToolsAdapter also bridges ADK's tool_context into the framework's
ToolContext, so session metadata (session_id, user_id, event_type) flows
through to handlers and logging.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agent_tools import ToolContext, weather_api  # triggers framework startup

# ``weather_api`` is an arbitrary handle — every ToolFunction exposes the
# same ``all_tools()`` / ``all_schemas()`` view over the shared registry.
_ALL_TOOL_FUNCTIONS = weather_api.all_tools()


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
