"""
ExecutorRouter — terminal middleware that dispatches to the handler.

Position in the pipeline
------------------------
The router is always the **innermost** link in the middleware chain — by
the time it runs, all cross-cutting middleware (auth, retry, proto
validation, logging) have already wrapped the call. Its job is trivial:
pick the handler instance, call ``execute(ctx)``, stash the result on
``ctx.result``, and return it.

Handler instance caching
------------------------
Handlers are instantiated **once per handler class** and cached for the
lifetime of the router. This matters because handlers often hold expensive
state: ``APIHandler`` has no state today, but ``CTAHandler`` could cache a
Dialogflow CX ``SessionsClient``, and user-defined handlers may hold
connection pools. Creating a fresh handler on every call would defeat that.

The cache is keyed on the ``type`` object itself (``handler_class``), not
on the tool name — so two ``type: api`` tools share one ``APIHandler``
instance. That's safe because handlers pass all per-call state through
:class:`ExecutionContext`; they never rely on instance attributes for
request-specific data.
"""
from __future__ import annotations

from typing import Any

from agent_tools.handlers.base import BaseHandler


class ExecutorRouter:
    """Dispatch to the correct handler — resolved from ToolDefinition.handler_class."""

    def __init__(self) -> None:
        # class → instance. Keyed on the class object to share handlers
        # across tools of the same type.
        self._instances: dict[type, BaseHandler] = {}

    def _get_handler(self, handler_class: type) -> BaseHandler:
        """Return a cached handler instance, creating it on first use."""
        if handler_class not in self._instances:
            self._instances[handler_class] = handler_class()
        return self._instances[handler_class]

    def wrap(self, next_fn: Any) -> Any:  # noqa: ARG002
        """
        Terminal ``wrap`` — ignores *next_fn* because there is nothing after
        the router. The pipeline builder will still pass a "terminal"
        sentinel to keep the chain-construction loop uniform; we just drop
        it on the floor.
        """
        async def _route(ctx: Any) -> Any:  # type: ignore[misc]
            handler = self._get_handler(ctx.tool_def.handler_class)
            ctx.result = await handler.execute(ctx)
            return ctx.result

        return _route