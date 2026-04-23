"""
LoggingMiddleware — emits structured log lines around every tool call.

Emits exactly one log line per call to the ``agent_tools`` logger:

* success::  ``tool=<name> [context fields] status=ok ms=<wall_clock_ms>``
* failure::  ``tool=<name> [context fields] status=error ms=<wall_clock_ms> error=<repr>``

Context fields (when present):
* ``session_id=<id>`` — request session identifier
* ``hashed_user_id=<sha256>`` — SHA-256 hash of user ID (privacy-safe)
* ``event_type=<type>`` — event classification (e.g. "adk_tool_call", "direct_call")
* ``timestamp=<iso8601>`` — UTC timestamp of the call

The timing is wall-clock around ``next_fn(ctx)`` — since this middleware
sits just above the router in the pipeline, that's effectively the
handler execution time plus schema-validation overhead. It does **not**
include retry backoff (retry sits outside this middleware, so each
attempt produces its own line pair with its own timing).

Logger configuration
--------------------
Calls ``logging.basicConfig(level=settings.log_level)`` in ``__init__``.
This is a no-op if the application has already configured logging, which
is the expected case in agent deployments — hosts typically own the
logging setup and we just emit into their configured handlers.

The key-value format ("``tool=X status=Y ms=Z``") is picked because it
parses cleanly with most log aggregators' key-value extractors without
needing a JSON encoder dependency. If you need JSON logs, drop a custom
``logging.Formatter`` on the ``agent_tools`` logger in your app startup.
"""

from __future__ import annotations

import logging
import time

from agent_tools.core.settings import Settings


class LoggingMiddleware:
    """Emits one structured log line per tool invocation."""

    def __init__(self, settings: Settings) -> None:
        self._log = logging.getLogger("agent_tools")
        # Ensure SOME logging config exists. If the host app already called
        # basicConfig, this is a no-op.
        logging.basicConfig(level=settings.log_level)

    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        """Return an async callable that logs timing/status around *next_fn*."""
        log = self._log

        async def _log(ctx):  # type: ignore[no-untyped-def]
            t0 = time.monotonic()
            try:
                result = await next_fn(ctx)
                log.info(
                    self._format_log(ctx.tool_def.name, ctx.tool_context, "ok", (time.monotonic() - t0) * 1000)
                )
                return result
            except Exception as exc:
                log.error(
                    self._format_log(ctx.tool_def.name, ctx.tool_context, "error", (time.monotonic() - t0) * 1000, exc)
                )
                # Always re-raise — the middleware observes, it doesn't swallow.
                raise

        return _log

    @staticmethod
    def _format_log(
        tool_name: str,
        tool_context,  # type: ignore[no-untyped-def]
        status: str,
        ms: float,
        error=None,  # type: ignore[no-untyped-def]
    ) -> str:
        """Build a structured log line with tool name, context, status, timing."""
        parts = [f"tool={tool_name}"]
        if tool_context:
            if tool_context.session_id:
                parts.append(f"session_id={tool_context.session_id}")
            if tool_context.hashed_user_id:
                parts.append(f"hashed_user_id={tool_context.hashed_user_id}")
            if tool_context.event_type:
                parts.append(f"event_type={tool_context.event_type}")
            if tool_context.timestamp:
                parts.append(f"timestamp={tool_context.timestamp}")
        parts.append(f"status={status} ms={ms:.1f}")
        if error:
            parts.append(f"error={error}")
        return " ".join(parts)
