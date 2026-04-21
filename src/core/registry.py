"""In-memory registry mapping tool names to their ToolDefinition."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_tools.core.definition import ToolDefinition


class ToolRegistry:
    """
    Simple dict-backed registry.

    Populated once at startup by :class:`~agent_tools.core.loader.ToolLoader`.
    Thread-safe for concurrent reads after initial population (no writes at
    call time).
    """

    def __init__(self) -> None:
        self._tools: dict[str, "ToolDefinition"] = {}

    def register(self, definition: "ToolDefinition") -> None:
        """Add *definition* to the registry.  Overwrites any existing entry with the same name."""
        self._tools[definition.name] = definition

    def get(self, name: str) -> "ToolDefinition":
        """
        Return the :class:`ToolDefinition` for *name*.

        :raises KeyError: if the tool is not registered.
        """
        if name not in self._tools:
            raise KeyError(
                f"Tool '{name}' is not registered. "
                f"Available tools: {self.names}"
            )
        return self._tools[name]

    @property
    def names(self) -> list[str]:
        """Sorted list of all registered tool names."""
        return sorted(self._tools.keys())

    def all(self) -> list["ToolDefinition"]:
        """All registered :class:`ToolDefinition` objects, in name order."""
        return [self._tools[n] for n in self.names]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
