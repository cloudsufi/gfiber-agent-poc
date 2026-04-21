"""LoggingMiddleware — emits structured log lines around every tool call."""
from __future__ import annotations

import logging
import time

from agent_tools.core.settings import Settings


class LoggingMiddleware:
    def __init__(self, settings: Settings) -> None:
        self._log = logging.getLogger("agent_tools")
        logging.basicConfig(level=settings.log_level)

    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        log = self._log

        async def _log(ctx):  # type: ignore[no-untyped-def]
            t0 = time.monotonic()
            try:
                result = await next_fn(ctx)
                log.info(
                    "tool=%s status=ok ms=%.1f",
                    ctx.tool_def.name,
                    (time.monotonic() - t0) * 1000,
                )
                return result
            except Exception as exc:
                log.error(
                    "tool=%s status=error ms=%.1f error=%s",
                    ctx.tool_def.name,
                    (time.monotonic() - t0) * 1000,
                    exc,
                )
                raise

        return _log
