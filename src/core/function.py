"""
ToolFunction — a self-contained callable that wraps ToolRuntime.execute().

Every tool import automatically carries the shared runtime and helpers so that
``runtime`` never needs to be imported separately::

    from agent_tools import check_billing

    result  = await check_billing(customer_id="CUST-001", period="2026-04")
    schemas = check_billing.all_schemas()   # no 'runtime' import needed
    tools   = check_billing.all_tools()
    rt      = check_billing.runtime         # still accessible if required
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_tools.core.runtime import ToolRuntime


class ToolFunction:
    """
    Callable wrapper for a single named tool.

    Instances are created by :mod:`agent_tools.__init__` and injected into the
    ``agent_tools`` namespace so that ``from agent_tools import <name>`` works.
    """

    def __init__(self, name: str, runtime: "ToolRuntime") -> None:
        self._name = name
        self._runtime = runtime
        self.__name__ = name          # looks like a real function in tracebacks
        self.__doc__ = (
            runtime._registry.get(name).description
            if name in runtime._registry
            else ""
        )

        # ── Public attributes — available on every tool import ────────────────
        self.runtime: "ToolRuntime" = runtime

    # ── Core call ─────────────────────────────────────────────────────────────

    async def __call__(self, **kwargs: Any) -> Any:
        """
        Execute the tool with the provided keyword arguments.

        Reserved kwarg ``_headers`` (dict[str, str]) — if present, its entries
        are merged into the request-scoped header context for the duration of
        this call only. They take precedence over static ``headers:`` values
        declared in ``tool.yaml`` and over auth-injected headers.
        """
        call_headers = kwargs.pop("_headers", None)
        if call_headers:
            from agent_tools.core.context import with_request_headers

            with with_request_headers(call_headers):
                return await self._runtime.execute(self._name, kwargs)
        return await self._runtime.execute(self._name, kwargs)

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

    def all_tools(self) -> list["ToolFunction"]:
        """Return all registered :class:`ToolFunction` objects."""
        return [
            ToolFunction(n, self._runtime)
            for n in self._runtime._registry.names
        ]

    # ── Dunder helpers ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<ToolFunction '{self._name}'>"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ToolFunction):
            return self._name == other._name and self._runtime is other._runtime
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._name)
