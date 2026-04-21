"""
ExecutorRouter — dispatches execution to the correct handler based on
``ctx.tool_def.handler_class``.

Handler instances are created on first use and cached for the lifetime of
the router instance.
"""
from __future__ import annotations

from typing import Any

from agent_tools.handlers.base import BaseHandler


class ExecutorRouter:
    """Dispatch to the correct handler — resolved from ToolDefinition.handler_class."""

    def __init__(self) -> None:
        self._instances: dict[type, BaseHandler] = {}

    def _get_handler(self, handler_class: type) -> BaseHandler:
        if handler_class not in self._instances:
            self._instances[handler_class] = handler_class()
        return self._instances[handler_class]

    def wrap(self, next_fn: Any) -> Any:  # noqa: ARG002
        async def _route(ctx: Any) -> Any:  # type: ignore[misc]
            handler = self._get_handler(ctx.tool_def.handler_class)
            ctx.result = await handler.execute(ctx)
            return ctx.result

        return _route