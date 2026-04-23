"""
agent_tools.middleware — per-call cross-cutting concerns.

Middleware is assembled into a linear chain by
:class:`~agent_tools.middleware.pipeline.MiddlewarePipeline`. Every tool call
flows through the same chain. The terminal link is the router, which picks
the correct :class:`~agent_tools.handlers.base.BaseHandler` from
``ctx.tool_def.handler_class``.

Execution order (outermost → innermost, i.e. the request's path)::

    AuthMiddleware            # resolves credentials once per call
        └── RetryMiddleware           # exponential backoff on exceptions
            └── SchemaValidationMiddleware  # validates input + output
                └── LoggingMiddleware          # wall-clock + status
                    └── ExecutorRouter             # picks handler, awaits it

The order matters. Auth is outermost so retries can re-use the resolved
credentials without re-fetching OAuth tokens on every attempt. Proto
validation sits inside retry so a transient handler error doesn't fail the
per-call input validation on the first attempt and succeed silently on the
second. Logging is innermost above the router so the timing it reports
corresponds to the handler execution itself (plus validation + routing).

Contract — every middleware class exposes one method::

    def wrap(self, next_fn) -> next_fn_async_callable: ...

``wrap`` receives the next link and returns an async callable that accepts
an :class:`~agent_tools.core.runtime.ExecutionContext` and returns the
tool's result. This is a manual decorator composition — no ASGI-style
classes — which keeps the framework's dependency surface tiny and makes
execution fully synchronous to follow in a debugger.

Adding a middleware
-------------------
1. Write a class with a ``wrap(next_fn)`` method returning an async function.
2. Append it to :meth:`MiddlewarePipeline.build`. Position carefully relative
   to the existing links — e.g. a "tenant" middleware that enriches logs
   should sit outside LoggingMiddleware; a "caching" middleware should sit
   inside SchemaValidationMiddleware so cached payloads round-trip cleanly.
"""
