"""
ToolFunction — a self-contained callable that wraps ToolRuntime.execute().

This is the public face of each tool. At framework import,
``agent_tools/__init__.py`` builds one :class:`ToolFunction` per registered
tool and injects it into the module namespace::

    from agent_tools import weather_api

    result  = await weather_api(city="London", units="metric", trace_id="t-1")
    schemas = weather_api.all_schemas()   # no 'runtime' import needed
    tools   = weather_api.all_tools()
    rt      = weather_api.runtime         # still accessible if required

Design goals
------------
1. **Single-line call site** — ``await tool(**kwargs)`` exactly matches how
   Python developers already expect to use an async function.
2. **Agent-friendly** — ``.schema`` exposes the ADK/LLM JSON Schema for the
   tool; ``.all_tools()`` / ``.all_schemas()`` let a caller wire every
   registered tool into an ``LlmAgent`` without touching the runtime.
3. **Runtime-injected headers** — the reserved ``_headers=`` kwarg is
   peeled off before validation and placed into the request-scoped
   :class:`ContextVar` for the duration of the call, but only reaches the
   wire if the tool's yaml declares ``runtime_headers``.

The object looks like a function in tracebacks (``__name__``) and in docs
(``__doc__`` pulled from the tool's description), but it's a full class so
we can attach schema / runtime helpers as attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_tools.core.runtime import ToolRuntime
    from agent_tools.core.tool_context import ToolContext


class ToolFunction:
    """
    Callable wrapper for a single named tool.

    Instances are created by :mod:`agent_tools.__init__` and injected into the
    ``agent_tools`` namespace so that ``from agent_tools import <name>`` works.
    """

    def __init__(self, name: str, runtime: ToolRuntime) -> None:
        self._name = name
        self._runtime = runtime
        self.__name__ = name  # looks like a real function in tracebacks
        self.__doc__ = runtime._registry.get(name).description if name in runtime._registry else ""

        # ── Public attributes — available on every tool import ────────────────
        self.runtime: ToolRuntime = runtime

    # ── Core call ─────────────────────────────────────────────────────────────

    async def __call__(
        self, tool_context: ToolContext, **kwargs: Any
    ) -> Any:
        """
        Execute the tool with session context and keyword arguments.

        :param tool_context: Session metadata (session_id, user_id, event_type,
            timestamp). This is the **first positional parameter** on every tool
            call. It is never part of the LLM-facing schema.
        :param kwargs: Tool input fields (corresponds to ``input.yaml``).
            Validation happens inside the runtime's middleware pipeline —
            unknown fields raise, type mismatches raise, missing required
            fields raise.

        Reserved kwarg: ``_headers`` (``dict[str, str]``)
            If supplied, the entries are pushed into the request-scoped
            :class:`ContextVar` for the duration of this call only. They are
            merged into the outgoing HTTP request **only if** the tool's
            ``tool.yaml`` declares a matching name in ``runtime_headers``.
            Without that opt-in, ``_headers`` is silently dropped.

        :returns: The handler's output, after being round-tripped through
            ``output.yaml`` (when declared; unknown response fields are
            silently dropped so external APIs that return extras don't break
            the contract).
        """
        call_headers = kwargs.pop("_headers", None)
        if call_headers:
            from agent_tools.core.context import with_request_headers

            with with_request_headers(call_headers):
                return await self._runtime.execute(
                    self._name, kwargs, tool_context=tool_context
                )
        return await self._runtime.execute(
            self._name, kwargs, tool_context=tool_context
        )

    # ── Schema helpers ────────────────────────────────────────────────────────

    @property
    def schema(self) -> dict[str, Any]:
        """This tool's ADK/LLM JSON-Schema dict."""
        return self._runtime._registry.get(self._name).adk_schema

    def all_schemas(self) -> list[dict[str, Any]]:
        """All registered tool schemas — for agent-wide LLM declarations."""
        return self._runtime.all_tool_schemas()

    def schemas_for(self, *names: str) -> list[dict[str, Any]]:
        """Schemas for a named subset of tools."""
        return self._runtime.tool_schemas_for(*names)

    # ── Tool list helper ──────────────────────────────────────────────────────

    def all_tools(self) -> list[ToolFunction]:
        """Return all registered :class:`ToolFunction` objects."""
        return [ToolFunction(n, self._runtime) for n in self._runtime._registry.names]

    # ── Dunder helpers ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<ToolFunction '{self._name}'>"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ToolFunction):
            return self._name == other._name and self._runtime is other._runtime
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._name)
