"""
ToolRuntime — the single execution entry point for the framework.

One :class:`ToolRuntime` is created at package import time (see
``agent_tools/__init__.py``). It owns:

* a :class:`ToolRegistry` populated by :class:`ToolLoader` at startup,
* a frozen :class:`Settings` read from ``AGENT_TOOLS_*`` env vars,
* a :class:`ToolTypeRegistry` mapping ``type`` strings to config schemas
  and handler classes,
* a :class:`MiddlewarePipeline` built once in ``__init__``.

Every tool call — whether via ``from agent_tools import my_tool``, via
``runtime.execute(name, kwargs)``, or via an ADK ``LlmAgent`` — ends up in
:meth:`ToolRuntime.execute`. That method looks the tool up in the registry
and hands the definition + kwargs to the middleware pipeline.

The :class:`ExecutionContext` defined in this module is the single object
that travels through the pipeline. Each middleware mutates it (``ctx.resolved_auth``,
``ctx.validated_input``, ``ctx.result``) and the handler reads from it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_tools.core.definition import ToolDefinition
from agent_tools.core.loader import ToolLoader
from agent_tools.core.registry import ToolRegistry
from agent_tools.core.settings import Settings
from agent_tools.core.type_registry import ToolTypeRegistry, default_type_registry


# ── Execution context ─────────────────────────────────────────────────────────

@dataclass
class ExecutionContext:
    """
    Carries the request and response data through the middleware pipeline.

    A fresh instance is created per :meth:`ToolRuntime.execute` call, so
    middleware may mutate its fields freely without worrying about leakage
    between calls.

    Fields
    ------
    tool_def
        The fully-resolved, config-validated :class:`ToolDefinition` for the
        tool being invoked. Read-only by convention.
    raw_kwargs
        The kwargs the caller passed to ``await tool(**kwargs)`` — exactly
        what the user supplied, before proto validation.
    validated_input
        Populated by :class:`ProtoValidationMiddleware` with ``raw_kwargs``
        after round-tripping through ``request.proto``. Unknown/typo fields
        are rejected here; missing required fields raise. Handlers should
        read from this, not from ``raw_kwargs``.
    resolved_auth
        Populated by :class:`AuthMiddleware`. Shape depends on the auth type:
        ``{"type": "bearer", "token": "..."}``,
        ``{"type": "api_key", "header": "...", "value": "..."}``,
        ``{"type": "basic", "encoded": "..."}``, or ``{}`` when no auth is
        configured.
    proto_input
        The compiled protobuf ``Message`` instance corresponding to
        ``validated_input`` — handy for handlers that want to forward the
        message over gRPC without re-encoding.
    result
        Set by the terminal router middleware to the handler's return value.
        Exposed primarily for post-handler middleware that needs to inspect
        the response.
    """

    tool_def: ToolDefinition
    raw_kwargs: dict[str, Any]
    validated_input: dict[str, Any] = field(default_factory=dict)
    resolved_auth: dict[str, Any] = field(default_factory=dict)
    proto_input: Any = field(default=None, repr=False)   # protobuf Message | None
    result: Any = field(default=None, repr=False)


# ── Runtime ───────────────────────────────────────────────────────────────────

class ToolRuntime:
    """
    Single entry-point for tool execution.

    Holds the registries and a pre-built middleware pipeline so the common
    case — "call a registered tool" — is a one-line lookup followed by a
    pipeline dispatch. Built once; thread-safe for concurrent reads.

    Usage::

        runtime = ToolRuntime.from_env()
        result  = await runtime.execute("weather_api", {"city": "London"})

    Agent code normally doesn't interact with :class:`ToolRuntime` directly —
    ``from agent_tools import weather_api`` returns a :class:`ToolFunction`
    that wraps this runtime for you.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        settings: Settings,
        type_registry: ToolTypeRegistry = default_type_registry,
    ) -> None:
        from agent_tools.middleware.pipeline import MiddlewarePipeline

        self._registry = registry
        self._settings = settings
        self._type_registry = type_registry
        self._pipeline = MiddlewarePipeline.build(settings)

    # ── factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_env(
        cls,
        type_registry: ToolTypeRegistry = default_type_registry,
    ) -> "ToolRuntime":
        """
        Load all tools from ``AGENT_TOOLS_DIR`` (or the package default),
        validate their configs, and return a ready :class:`ToolRuntime`.

        This is the factory used at package import time. It will raise
        eagerly if any tool.yaml is malformed or references an unknown
        tool type — by the time this returns, every registered tool is
        guaranteed to be callable.

        :param type_registry: optional override for the default
            :class:`ToolTypeRegistry`. Supply a custom registry if you want
            to expose additional tool types that aren't registered globally.
        """
        settings = Settings.load()
        loader = ToolLoader(type_registry=type_registry)
        registry = ToolRegistry()
        for defn in loader.load_all(Path(settings.tools_dir)):
            registry.register(defn)
        return cls(registry=registry, settings=settings, type_registry=type_registry)

    # ── execution ─────────────────────────────────────────────────────────────

    async def execute(self, tool_name: str, kwargs: dict[str, Any]) -> Any:
        """
        Run *tool_name* with *kwargs* through the full middleware pipeline.

        ``kwargs`` is what the user passed on the outside (e.g.
        ``{"customer_id": "X", "period": "2026-04"}``). It is placed on the
        fresh :class:`ExecutionContext` as ``raw_kwargs`` and then
        :class:`ProtoValidationMiddleware` round-trips it through
        ``request.proto`` into ``ctx.validated_input``.

        The returned value is whatever the handler returned, after output
        validation against ``response.proto`` (when declared; unknown fields
        are silently dropped so external APIs that return extras still work).

        :raises KeyError: if *tool_name* is not registered.
        :raises ValueError: on input / output proto validation failure.
        :raises Exception: anything the handler raises (bubbles up through
            the retry middleware's last attempt).
        """
        definition = self._registry.get(tool_name)
        return await self._pipeline.run(definition, kwargs)

    # ── schema helpers ────────────────────────────────────────────────────────

    def tool_schemas_for(self, *names: str) -> list[dict[str, Any]]:
        """Return ADK/LLM JSON-Schema dicts for the named tools."""
        return [self._registry.get(n).adk_schema for n in names]

    def all_tool_schemas(self) -> list[dict[str, Any]]:
        """Return ADK/LLM JSON-Schema dicts for every registered tool."""
        return [d.adk_schema for d in self._registry.all()]
