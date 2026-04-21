"""
Registry that maps tool type names to their config schema and handler class.

Built-in types are registered via :func:`_make_default_registry` at module
import time.  Third-party types use :meth:`ToolTypeRegistry.register` — no
changes to framework code required.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_tools.core.definition import ToolTypeEntry

if TYPE_CHECKING:
    pass

# Absolute path to the bundled schemas directory
_SCHEMAS: Path = Path(__file__).parent.parent / "schemas"


class ToolTypeRegistry:
    """
    Maps tool type name strings to :class:`~agent_tools.core.definition.ToolTypeEntry`
    objects (config schema path + handler class).
    """

    def __init__(self) -> None:
        self._entries: dict[str, ToolTypeEntry] = {}

    def register(
        self,
        name: str,
        config_proto_path: Path,
        handler_class: Any,  # type: ignore[misc]
    ) -> None:
        """
        Register a tool type.

        :param name:               Type identifier used in ``tool.yaml`` (e.g. ``"api"``).
        :param config_proto_path:  Absolute path to the config ``.proto`` schema.
        :param handler_class:      Handler class (subclass of
                                   :class:`~agent_tools.handlers.base.BaseHandler`).
        """
        self._entries[name] = ToolTypeEntry(
            name=name,
            config_proto_path=config_proto_path,
            handler_class=handler_class,
        )

    def get(self, name: str) -> ToolTypeEntry:
        """
        Return the :class:`ToolTypeEntry` for *name*.

        :raises KeyError: if the type is not registered.
        """
        if name not in self._entries:
            raise KeyError(
                f"Unknown tool type '{name}'. "
                f"Registered types: {self.known_types()}"
            )
        return self._entries[name]

    def known_types(self) -> list[str]:
        """Sorted list of all registered type names."""
        return sorted(self._entries.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._entries


def _make_default_registry() -> ToolTypeRegistry:
    """Build and return the registry pre-loaded with all built-in tool types."""
    # Deferred imports so that importing this module doesn't pull in httpx / grpc
    # until actually needed.
    from agent_tools.handlers.api_handler import APIHandler
    from agent_tools.handlers.bigquery_handler import BigQueryHandler
    from agent_tools.handlers.grpc_handler import GRPCHandler
    from agent_tools.handlers.mcp_handler import MCPHandler
    from agent_tools.handlers.python_handler import PythonHandler
    from agent_tools.handlers.rest_handler import RESTHandler

    r = ToolTypeRegistry()
    r.register("api", _SCHEMAS / "api_tool_config.proto", APIHandler)
    r.register("mcp", _SCHEMAS / "mcp_tool_config.proto", MCPHandler)
    r.register("python", _SCHEMAS / "python_tool_config.proto", PythonHandler)
    r.register("grpc", _SCHEMAS / "grpc_tool_config.proto", GRPCHandler)
    r.register("bigquery", _SCHEMAS / "bigquery_tool_config.proto", BigQueryHandler)
    r.register("rest", _SCHEMAS / "rest_tool_config.proto", RESTHandler)
    return r


# Module-level singleton — shared across the entire process.
default_type_registry: ToolTypeRegistry = _make_default_registry()
