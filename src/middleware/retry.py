"""
RetryMiddleware — wraps execution with exponential back-off retry logic.

Retry count comes from ``ctx.tool_def.execution.retries``, falling back to
``Settings.default_retries`` (``AGENT_TOOLS_RETRIES``, default 3) when the
tool left the sentinel ``-1`` in its execution block. A value of ``0``
means "try once, never retry".

Every ``Exception`` triggers a retry — this is deliberately broad. The
framework can't know which exceptions are transient for every possible
handler (an HTTP 5xx, a DNS failure, a transient gRPC RESOURCE_EXHAUSTED,
a Dialogflow CX quota error), so we retry everything and let the total
retry count be the safety bound. Tools that know better can set
``retries: 0`` to opt out.

Backoff is exponential: ``2**attempt`` seconds (1s, 2s, 4s, 8s, …). There
is no jitter today; add it if thundering-herd becomes a real problem.

The middleware sits **inside** auth (so OAuth tokens aren't re-fetched on
every attempt) and **outside** proto validation (so a malformed request
surfaces once as a validation error, not as N retried validation errors).
"""
from __future__ import annotations

import asyncio

from agent_tools.core.settings import Settings


class RetryMiddleware:
    """
    Retries the inner chain up to ``retries`` additional times on exception.

    ``retries=3`` means 1 initial attempt + 3 retries = 4 total attempts.
    Sleep between attempts is ``2**attempt`` seconds, so
    attempt 0 → 1 → 2 → 3 waits 1s, 2s, 4s.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        """Return an async callable that wraps *next_fn* with retry logic."""
        settings = self._settings

        async def _retry(ctx):  # type: ignore[no-untyped-def]
            # Resolve sentinel (-1) values against the global Settings once
            # per call, not per attempt — this keeps the retry count stable
            # even if Settings is reloaded between calls (which shouldn't
            # happen, but let's be defensive).
            cfg = ctx.tool_def.execution.resolved(settings)
            last_exc: Exception | None = None
            for attempt in range(cfg.retries + 1):
                try:
                    return await next_fn(ctx)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < cfg.retries:
                        await asyncio.sleep(2**attempt)
            # All attempts exhausted — re-raise the last exception. The
            # ``last_exc`` can't be None here because the loop body either
            # returned or caught.
            raise last_exc  # type: ignore[misc]

        return _retry
