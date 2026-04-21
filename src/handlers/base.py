"""Abstract base class for all tool handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class BaseHandler(ABC):
    """Every handler must implement :meth:`execute`."""

    @abstractmethod
    async def execute(self, ctx: "ExecutionContext") -> Any:
        """Execute the tool and return a result dict (or any JSON-serialisable value)."""
        ...