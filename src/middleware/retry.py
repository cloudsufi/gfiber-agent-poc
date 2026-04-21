"""RetryMiddleware — wraps execution with exponential back-off retry logic."""
from __future__ import annotations

import asyncio

from agent_tools.core.settings import Settings


class RetryMiddleware:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        settings = self._settings

        async def _retry(ctx):  # type: ignore[no-untyped-def]
            cfg = ctx.tool_def.execution.resolved(settings)
            last_exc: Exception | None = None
            for attempt in range(cfg.retries + 1):
                try:
                    return await next_fn(ctx)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < cfg.retries:
                        await asyncio.sleep(2**attempt)
            raise last_exc  # type: ignore[misc]

        return _retry
