"""
ToolRuntime — the single execution entry point.

Initialise once at startup; all tools are loaded, config-validated, and ready.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_tools.core.definition import ToolDefinition
from agent_tools.core.loader import ToolLoader
from agent_tools.core.registry import ToolRegistry
from agent_tools.core.settings import Settings
from agent_tools.core.type_registry import ToolTypeRegistry, default_type_registry


# ── Execution context ─────────────────────────────────────────────────────────

@dataclass
class ExecutionContext:
    """
    Carries the request and response data through the middleware pipeline.

    Created fresh for every :meth:`ToolRuntime.execute` call.
    """

    tool_def: ToolDefinition
    raw_kwargs: dict[str, Any]
    validated_input: dict[str, Any] = field(default_factory=dict)
    resolved_auth: dict[str, Any] = field(default_factory=dict)
    proto_input: Any = field(default=None, repr=False)   # protobuf Message | None
    result: Any = field(default=None, repr=False)


# ── Runtime ───────────────────────────────────────────────────────────────────

class ToolRuntime:
    """
    Single entry-point for tool execution.

    Usage::

        runtime = ToolRuntime.from_env()
        result  = await runtime.execute("check_billing", {"customer_id": "X"})
    """

    def __init__(
        self,
        registry: ToolRegistry,
        settings: Settings,
        type_registry: ToolTypeRegistry = default_type_registry,
    ) -> None:
        from agent_tools.middleware.pipeline import MiddlewarePipeline

        self._registry = registry
        self._settings = settings
        self._type_registry = type_registry
        self._pipeline = MiddlewarePipeline.build(settings)

    # ── factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_env(
        cls,
        type_registry: ToolTypeRegistry = default_type_registry,
    ) -> "ToolRuntime":
        """
        Load all tools from ``AGENT_TOOLS_DIR`` (or the package default),
        validate their configs, and return a ready :class:`ToolRuntime`.
        """
        settings = Settings.load()
        loader = ToolLoader(type_registry=type_registry)
        registry = ToolRegistry()
        for defn in loader.load_all(Path(settings.tools_dir)):
            registry.register(defn)
        return cls(registry=registry, settings=settings, type_registry=type_registry)

    # ── execution ─────────────────────────────────────────────────────────────

    async def execute(self, tool_name: str, kwargs: dict[str, Any]) -> Any:
        """Run *tool_name* with *kwargs* through the full middleware pipeline."""
        definition = self._registry.get(tool_name)
        return await self._pipeline.run(definition, kwargs)

    # ── schema helpers ────────────────────────────────────────────────────────

    def tool_schemas_for(self, *names: str) -> list[dict[str, Any]]:
        """Return ADK/LLM JSON-Schema dicts for the named tools."""
        return [self._registry.get(n).adk_schema for n in names]

    def all_tool_schemas(self) -> list[dict[str, Any]]:
        """Return ADK/LLM JSON-Schema dicts for every registered tool."""
        return [d.adk_schema for d in self._registry.all()]
