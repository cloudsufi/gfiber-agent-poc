"""
Registry that maps tool type names to their config schema and handler class.

This is what turns a bare ``type: api`` string in a tool.yaml into the two
concrete dependencies the loader needs: (1) a path to the ``.proto`` schema
used to validate the ``config:`` block, and (2) the handler class that will
run the tool at call time.

The four primary types (``api``, ``mcp``, ``function``, ``cta``) are
registered at module import time by :func:`_make_default_registry`. Anyone
can register a new type **before** ``import agent_tools`` completes, and
the loader will pick it up::

    from pathlib import Path
    import agent_tools.core.type_registry as tr
    from my_package.handlers import KafkaHandler

    tr.default_type_registry.register(
        "kafka",
        Path("src/schemas/kafka_tool_config.proto"),
        KafkaHandler,
    )
    import agent_tools  # now tools with `type: kafka` load successfully

Late registration (after the tools have already loaded) is allowed but
only affects tools loaded afterwards — the existing ones keep whatever
handler class was resolved when they were loaded.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_tools.core.definition import ToolTypeEntry

# Absolute path to the bundled schemas directory
_SCHEMAS: Path = Path(__file__).parent.parent / "schemas"


class ToolTypeRegistry:
    """Maps tool type name strings to :class:`ToolTypeEntry` objects."""

    def __init__(self) -> None:
        self._entries: dict[str, ToolTypeEntry] = {}

    def register(
        self,
        name: str,
        config_proto_path: Path,
        handler_class: Any,  # type: ignore[misc]
    ) -> None:
        """Register a tool type.

        :param name:               Type identifier used in ``tool.yaml`` (e.g. ``"api"``).
        :param config_proto_path:  Absolute path to the config ``.proto`` schema.
        :param handler_class:      Handler class (subclass of :class:`BaseHandler`).
        """
        self._entries[name] = ToolTypeEntry(
            name=name,
            config_proto_path=config_proto_path,
            handler_class=handler_class,
        )

    def get(self, name: str) -> ToolTypeEntry:
        """Return the :class:`ToolTypeEntry` for *name*.

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
    """Build and return the registry pre-loaded with the four primary types."""
    # Deferred imports — importing this module shouldn't pull handler deps
    # until the framework actually needs them.
    from agent_tools.handlers.api_handler import APIHandler
    from agent_tools.handlers.cta_handler import CTAHandler
    from agent_tools.handlers.function_handler import FunctionHandler
    from agent_tools.handlers.mcp_handler import MCPHandler

    r = ToolTypeRegistry()
    r.register("api",      _SCHEMAS / "api_tool_config.proto",      APIHandler)
    r.register("mcp",      _SCHEMAS / "mcp_tool_config.proto",      MCPHandler)
    r.register("function", _SCHEMAS / "function_tool_config.proto", FunctionHandler)
    r.register("cta",      _SCHEMAS / "cta_tool_config.proto",      CTAHandler)
    return r


# Module-level singleton — shared across the entire process.
default_type_registry: ToolTypeRegistry = _make_default_registry()
