"""
Abstract base class for every tool handler.

A handler is the strategy that actually invokes the tool. The framework
routes to it through :class:`ExecutorRouter` — the terminal middleware —
so by the time ``execute`` runs:

* ``ctx.validated_input`` has passed the ``input.yaml`` round-trip.
* ``ctx.resolved_auth`` has been populated by :class:`AuthMiddleware`.
* ``ctx.tool_def.config`` is the normalized yaml config (validated against
  the type's config schema).
* Retries and logging wrap the call from outside — individual handlers
  never need to implement either concern.

The return value is whatever is semantically right for the tool; it flows
back through :class:`SchemaValidationMiddleware`, which round-trips it
through ``output.yaml`` (when declared), dropping unknown fields so an
external API's extra payload keys don't break the contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class BaseHandler(ABC):
    """
    Every handler must implement :meth:`execute`.

    Handlers are instantiated lazily by :class:`ExecutorRouter` on first use
    and cached for the lifetime of the runtime — so ``__init__`` is the
    right place to set up expensive state (connection pools, SDK clients).
    ``execute`` is called once per tool invocation.
    """

    @abstractmethod
    async def execute(self, ctx: ExecutionContext) -> Any:
        """
        Execute the tool and return its result.

        :param ctx: Populated :class:`ExecutionContext`. Handlers read config
            from ``ctx.tool_def.config``, input from ``ctx.validated_input``,
            credentials from ``ctx.resolved_auth``.
        :returns: A JSON-serialisable value. When the tool declares a
            ``output.yaml``, this is validated by the middleware before
            the caller sees it; unknown response fields are dropped rather
            than raising.
        :raises Exception: Any error is caught by :class:`RetryMiddleware`
            first. If retries are exhausted, the exception propagates to
            the caller.
        """
        ...
