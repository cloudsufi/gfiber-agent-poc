"""
MiddlewarePipeline — builds and runs the ordered middleware chain.

Each middleware wraps the next via ``wrap(next_fn) -> next_fn``.
The chain is built right-to-left so the first middleware listed is the
outermost (first to run on the way in, last on the way out).
"""
from __future__ import annotations

from typing import Any, Callable

from agent_tools.core.definition import ToolDefinition
from agent_tools.core.settings import Settings

Next = Callable[..., Any]   # async (ExecutionContext) -> Any


class MiddlewarePipeline:
    def __init__(self, middlewares: list) -> None:
        self._middlewares = middlewares

    @classmethod
    def build(cls, settings: Settings) -> "MiddlewarePipeline":
        """Construct the default pipeline with all built-in middleware."""
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
        """Execute *kwargs* through the full middleware chain for *tool_def*."""
        from agent_tools.core.runtime import ExecutionContext

        ctx = ExecutionContext(tool_def=tool_def, raw_kwargs=kwargs)

        async def terminal(c: ExecutionContext) -> Any:  # type: ignore[misc]
            raise RuntimeError("Pipeline ended without a handler — check ExecutorRouter.")

        chain: Next = terminal
        for mw in reversed(self._middlewares):
            chain = mw.wrap(chain)

        return await chain(ctx)
