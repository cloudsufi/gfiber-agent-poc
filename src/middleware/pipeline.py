"""
MiddlewarePipeline — builds and runs the ordered middleware chain.

Each middleware exposes a ``wrap(next_fn) -> next_fn`` method. The pipeline
builds the chain right-to-left (innermost link first), so the middleware
that appears **first** in the list is the **outermost** wrapper — the
first to see the request on the way in, the last to see the result on the
way out.

Default order (outermost → innermost)::

    AuthMiddleware              ← resolves credentials once per call
    RetryMiddleware             ← retries the inner chain on exception
    ProtoValidationMiddleware   ← validates input + output against proto
    LoggingMiddleware           ← structured before/after log lines
    ExecutorRouter              ← terminal: dispatches to the handler

Why this specific order
-----------------------
* **Auth outside retry** — one OAuth token per call, not per attempt.
* **Retry outside proto validation** — a 5xx from the service triggers a
  retry; a malformed request does not (it raises at validation and never
  reaches the handler).
* **Logging innermost above the router** — the reported timing is the
  handler call, not the full pipeline round-trip.

Extensibility
-------------
To add a new middleware, subclass or compose with something exposing
``wrap(next_fn)`` and add it to :meth:`build` in the right position.
"""
from __future__ import annotations

from typing import Any, Callable

from agent_tools.core.definition import ToolDefinition
from agent_tools.core.settings import Settings

Next = Callable[..., Any]   # async (ExecutionContext) -> Any


class MiddlewarePipeline:
    """
    Holds an ordered list of middleware objects and composes them per call.

    The list is ordered outermost → innermost. The ``run`` method walks it
    in reverse, calling ``wrap`` on each to produce the final async
    callable, then invokes that with a fresh :class:`ExecutionContext`.
    """

    def __init__(self, middlewares: list) -> None:
        self._middlewares = middlewares

    @classmethod
    def build(cls, settings: Settings) -> "MiddlewarePipeline":
        """
        Construct the default pipeline with all built-in middleware.

        Middleware imports are deferred into this method so importing the
        pipeline module doesn't pull in httpx, google-auth, etc. until the
        pipeline is actually built (once, at runtime construction time).
        """
        from agent_tools.handlers.router import ExecutorRouter
        from agent_tools.middleware.auth import AuthMiddleware
        from agent_tools.middleware.logging import LoggingMiddleware
        from agent_tools.middleware.proto_validation import ProtoValidationMiddleware
        from agent_tools.middleware.retry import RetryMiddleware

        return cls(
            [
                AuthMiddleware(),
                RetryMiddleware(settings),
                ProtoValidationMiddleware(),
                LoggingMiddleware(settings),
                ExecutorRouter(),
            ]
        )

    async def run(self, tool_def: ToolDefinition, kwargs: dict[str, Any]) -> Any:
        """
        Execute *kwargs* through the full middleware chain for *tool_def*.

        Builds a fresh :class:`ExecutionContext`, composes the middleware
        chain (cheap — just function wrapping, no awaiting), and awaits the
        outermost callable. The pipeline is stateless per call — every
        invocation gets its own context and its own chain of closures.

        The ``terminal`` function at the bottom exists to catch a
        configuration bug: if :class:`ExecutorRouter` is somehow not
        included in the middleware list, the chain would end without a
        handler ever being called. The terminal raises instead of silently
        returning ``None``.
        """
        from agent_tools.core.runtime import ExecutionContext

        ctx = ExecutionContext(tool_def=tool_def, raw_kwargs=kwargs)

        async def terminal(c: ExecutionContext) -> Any:  # type: ignore[misc]
            raise RuntimeError("Pipeline ended without a handler — check ExecutorRouter.")

        chain: Next = terminal
        for mw in reversed(self._middlewares):
            chain = mw.wrap(chain)

        return await chain(ctx)
