"""
Demo ADK agent that consumes tools from the ``agent_tools`` package.

The agent is built from every tool registered by ``agent_tools`` at import
time — no manual wiring. Each ``ToolFunction`` is wrapped in a thin
:class:`AgentToolsAdapter` so ADK can discover its JSON-Schema declaration
(derived from the tool's ``request.proto``) and dispatch calls into the
framework runtime.
"""
from __future__ import annotations

from typing import Any

from agent_tools import enrich_lead  # triggers framework startup

# ``enrich_lead`` is an arbitrary handle — every ToolFunction exposes the
# same ``all_tools()`` / ``all_schemas()`` view over the shared registry.
_ALL_TOOL_FUNCTIONS = enrich_lead.all_tools()


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
                return await self._tool_fn(**args)

        return _Adapter(tool_fn)
