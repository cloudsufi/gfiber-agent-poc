"""
ToolLoader — scans a tools directory and builds native ``google.adk.tools.*``
instances from validated YAML configs.

Usage
-----
Synchronous (OpenAPI + Function tools):

    from adk_tools.loader import ToolLoader

    tools = ToolLoader().load_sync("tools/")
    agent = LlmAgent(model="gemini-2.0-flash", tools=tools, ...)

Asynchronous (all tools, including MCP):

    from adk_tools.loader import ToolLoader

    tools, exit_stack = await ToolLoader().load_async("tools/")
    async with exit_stack:
        agent = LlmAgent(model="gemini-2.0-flash", tools=tools, ...)
        runner = Runner(agent=agent, ...)
        ...

Tool type → ADK class mapping
------------------------------
==========  =====================================================================
 type        google.adk class used
==========  =====================================================================
 openapi     ``google.adk.tools.openapi_tool.OpenAPIToolset``
             Parses the tool's ``openapi.yaml`` spec, applies auth, and returns
             the toolset's list of ``RestApiTool`` objects.  One tool.yaml can
             expose multiple operations if ``operation_id`` is not restricted.
 mcp         ``google.adk.tools.mcp_tool.MCPToolset``
             Opens an SSE or stdio connection to an MCP server and returns its
             tools.  Requires ``load_async`` because the MCP handshake is async.
             An ``AsyncExitStack`` is returned so callers can close connections.
 function    ``google.adk.tools.FunctionTool``
             Loads ``logic.py`` from the tool directory, looks up the configured
             function, and wraps it.  Static ``parameters`` from the config are
             merged into every call as keyword arguments.

             ToolContext injection
             ~~~~~~~~~~~~~~~~~~~~
             If the function in ``logic.py`` declares a ``tool_context``
             parameter typed as ``google.adk.tools.tool_context.ToolContext``,
             ADK will inject the live session context automatically.  This works
             whether or not static ``parameters`` are configured — the loader
             preserves the full ``inspect.signature`` on any wrapper it creates
             so ADK always sees the correct parameter list.
==========  =====================================================================
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import warnings
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable

import yaml

from .auth import build_mcp_headers, build_openapi_auth
from .models import FunctionConfig, MCPConfig, OpenAPIConfig, ToolDef, load_tool_def

log = logging.getLogger("adk_tools.loader")


# ── Signature-preserving wrapper ───────────────────────────────────────────────


def _wrap_with_static_params(
    original: Callable,
    *,
    static: dict[str, Any],
    name: str,
    doc: str,
) -> Callable:
    """
    Return an async wrapper around *original* that pre-fills *static* keyword
    arguments on every call, while preserving the original's full
    ``inspect.signature`` so ADK can:

    1. Detect and inject ``tool_context`` (by name + ``ToolContext`` annotation).
    2. Generate the correct LLM schema (parameter names, types, descriptions).

    Parameters covered by *static* are **removed** from the visible signature
    so they never appear in the LLM schema — they are internal implementation
    details injected server-side.

    How ``__signature__`` grafting works
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Python's ``inspect.signature()`` honours ``__signature__`` when present,
    so setting it on the wrapper makes ADK (and any other caller of
    ``inspect.signature``) see the curated parameter list instead of the
    wrapper's actual ``(**kwargs)`` parameters.
    """
    sig = inspect.signature(original)
    all_params = sig.parameters

    has_tool_context = "tool_context" in all_params

    # Build the signature ADK will see:
    # - drop parameters covered by static config (hidden from LLM)
    # - keep tool_context so ADK injects it
    visible_params = [
        p for p_name, p in all_params.items()
        if p_name not in static
    ]

    if has_tool_context:
        async def _wrapped(tool_context: Any = None, **kwargs: Any) -> Any:
            return await original(tool_context=tool_context, **{**static, **kwargs})
    else:
        async def _wrapped(**kwargs: Any) -> Any:  # type: ignore[misc]
            return await original(**{**static, **kwargs})

    # Graft the cleaned signature — inspect.signature(_wrapped) returns this.
    _wrapped.__signature__ = sig.replace(parameters=visible_params)  # type: ignore[attr-defined]

    # Rebuild __annotations__ from the visible params + return type.
    ann: dict[str, Any] = {
        p.name: p.annotation
        for p in visible_params
        if p.annotation is not inspect.Parameter.empty
    }
    if sig.return_annotation is not inspect.Parameter.empty:
        ann["return"] = sig.return_annotation
    _wrapped.__annotations__ = ann

    _wrapped.__name__ = name or original.__name__
    _wrapped.__doc__ = doc or original.__doc__ or ""
    return _wrapped


class ToolLoader:
    """
    Scan a directory of tool sub-folders, validate each ``tool.yaml`` config,
    and instantiate the corresponding ``google.adk.tools.*`` object.

    Every validation error raises immediately (fail-fast) so a broken
    config is never silently swallowed and later surfaced mid-conversation.
    """

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_sync(self, tools_dir: str | Path = "tools") -> list[Any]:
        """
        Build ADK tool objects for **OpenAPI** and **Function** tool types.

        MCP tools are skipped with a warning because they require an async
        handshake — use :meth:`load_async` to include them.

        :param tools_dir: Path to the directory containing tool sub-folders.
        :returns: List of native ADK tool objects ready for
            ``LlmAgent(tools=[...])``.
        """
        tools_dir = Path(tools_dir)
        adk_tools: list[Any] = []

        for tool_dir in self._iter_tool_dirs(tools_dir):
            defn = load_tool_def(tool_dir)

            if defn.config.type == "openapi":
                built = self._build_openapi(defn, tool_dir)
                adk_tools.extend(built)
                log.debug("Loaded OpenAPI tool '%s' → %d ADK tool(s)", defn.name, len(built))

            elif defn.config.type == "function":
                built_fn = self._build_function(defn, tool_dir)
                adk_tools.append(built_fn)
                log.debug("Loaded Function tool '%s'", defn.name)

            elif defn.config.type == "mcp":
                warnings.warn(
                    f"Tool '{defn.name}' has type 'mcp' which requires async initialisation. "
                    "Use ToolLoader().load_async() to include MCP tools.",
                    stacklevel=2,
                )

        return adk_tools

    async def load_async(
        self, tools_dir: str | Path = "tools"
    ) -> tuple[list[Any], AsyncExitStack]:
        """
        Build ADK tool objects for **all** tool types, including MCP.

        Returns ``(tools, exit_stack)``. The caller is responsible for
        keeping *exit_stack* alive for the lifetime of the agent session
        so MCP server connections remain open::

            tools, exit_stack = await loader.load_async("tools/")
            async with exit_stack:
                agent = LlmAgent(..., tools=tools)
                # run agent here

        :param tools_dir: Path to the directory containing tool sub-folders.
        :returns: Tuple of (list of ADK tools, AsyncExitStack for cleanup).
        """
        tools_dir = Path(tools_dir)
        exit_stack = AsyncExitStack()
        adk_tools: list[Any] = []

        for tool_dir in self._iter_tool_dirs(tools_dir):
            defn = load_tool_def(tool_dir)

            if defn.config.type == "openapi":
                built = self._build_openapi(defn, tool_dir)
                adk_tools.extend(built)
                log.debug("Loaded OpenAPI tool '%s' → %d ADK tool(s)", defn.name, len(built))

            elif defn.config.type == "function":
                adk_tools.append(self._build_function(defn, tool_dir))
                log.debug("Loaded Function tool '%s'", defn.name)

            elif defn.config.type == "mcp":
                mcp_tools = await self._build_mcp(defn, exit_stack)
                adk_tools.extend(mcp_tools)
                log.debug("Loaded MCP tool '%s' → %d ADK tool(s)", defn.name, len(mcp_tools))

        return adk_tools, exit_stack

    # ── OpenAPI builder ────────────────────────────────────────────────────────

    def _build_openapi(self, defn: ToolDef, tool_dir: Path) -> list[Any]:
        """
        Build ``google.adk.tools.openapi_tool.OpenAPIToolset`` from the tool's
        OpenAPI spec and return its list of ``RestApiTool`` instances.

        The toolset exposes **all operations** in the spec unless you use
        ``get_tool(operation_id)`` filtering (see ADK docs for per-operation
        toolsets).  Wrap in a single-operation tool.yaml per operation if
        you need per-operation auth or config overrides.
        """
        try:
            from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import (  # type: ignore[import]
                OpenAPIToolset,
            )
        except ImportError as exc:
            raise ImportError(
                "google-adk is required for OpenAPI tools. "
                "Install: pip install google-adk"
            ) from exc

        cfg: OpenAPIConfig = defn.config  # type: ignore[assignment]
        spec_path = tool_dir / cfg.spec_file
        spec: dict = yaml.safe_load(spec_path.read_text())

        auth_scheme, auth_credential = build_openapi_auth(cfg.auth)

        toolset = OpenAPIToolset(
            spec_dict=spec,
            auth_scheme=auth_scheme,
            auth_credential=auth_credential,
        )
        return toolset.get_tools()

    # ── MCP builder ────────────────────────────────────────────────────────────

    async def _build_mcp(self, defn: ToolDef, exit_stack: AsyncExitStack) -> list[Any]:
        """
        Build ``google.adk.tools.mcp_tool.MCPToolset`` tools.

        Opens the MCP server connection (SSE or stdio), registers teardown
        in *exit_stack*, optionally filters to :attr:`MCPConfig.tool_filter`,
        and returns the list of ``MCPTool`` instances.
        """
        try:
            from google.adk.tools.mcp_tool.mcp_toolset import (  # type: ignore[import]
                MCPToolset,
                SseServerParams,
                StdioServerParams,
            )
        except ImportError as exc:
            raise ImportError(
                "google-adk with MCP support is required. "
                "Install: pip install 'google-adk[mcp]'"
            ) from exc

        cfg: MCPConfig = defn.config  # type: ignore[assignment]

        if cfg.server_url:
            # ── SSE transport ─────────────────────────────────────────────────
            headers = build_mcp_headers(cfg.auth)
            params = SseServerParams(url=cfg.server_url, headers=headers)
        else:
            # ── Stdio transport ───────────────────────────────────────────────
            import os

            env = {**os.environ, **cfg.env_vars} if cfg.env_vars else None
            params = StdioServerParams(
                command=cfg.command,
                args=cfg.args,
                env=env,
            )

        # MCPToolset.from_server opens the connection and returns
        # (list[MCPTool], AsyncExitStack) — register the inner stack so
        # the caller's exit_stack closes the connection on teardown.
        tools, mcp_exit_stack = await MCPToolset.from_server(connection_params=params)
        await exit_stack.enter_async_context(mcp_exit_stack)

        if cfg.tool_filter:
            filter_set = set(cfg.tool_filter)
            tools = [t for t in tools if t.name in filter_set]
            log.debug(
                "MCP tool '%s': filtered to %d tool(s) from %s",
                defn.name,
                len(tools),
                cfg.tool_filter,
            )

        return tools

    # ── Function builder ───────────────────────────────────────────────────────

    def _build_function(self, defn: ToolDef, tool_dir: Path) -> Any:
        """
        Load ``logic.py`` from *tool_dir*, retrieve the configured function,
        optionally wrap it with static parameters, and return a
        ``google.adk.tools.FunctionTool``.

        The function in ``logic.py`` must be **async**.  ADK generates the
        LLM tool schema from the function's signature + docstring::

            # logic.py
            from google.adk.tools.tool_context import ToolContext

            async def run(
                city: str,
                tool_context: ToolContext,      # ADK injects this automatically
                units: str = "metric",
            ) -> dict:
                \"\"\"Return current weather for a city.\"\"\"
                session_id = tool_context.state.get("session_id", "")
                ...

        ``tool_context`` is never exposed in the LLM schema — ADK recognises
        the parameter by name + type and injects it before calling the function.
        This works transparently even when ``config.parameters`` are configured,
        because :func:`_wrap_with_static_params` grafts the original
        ``inspect.signature`` (including ``tool_context``) onto the wrapper.
        """
        try:
            from google.adk.tools import FunctionTool  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk is required for Function tools. "
                "Install: pip install google-adk"
            ) from exc

        cfg: FunctionConfig = defn.config  # type: ignore[assignment]
        logic_path = tool_dir / "logic.py"

        # Load logic.py as a module scoped to this tool's name so multiple
        # tools' logic.py files don't shadow each other in sys.modules.
        module_name = f"adk_tools._logic.{defn.name}"
        mod_spec = importlib.util.spec_from_file_location(module_name, logic_path)
        if mod_spec is None or mod_spec.loader is None:
            raise ImportError(f"Cannot create module spec from: {logic_path}")

        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)  # type: ignore[union-attr]

        func = getattr(module, cfg.function, None)
        if func is None:
            raise AttributeError(
                f"Tool '{defn.name}': function '{cfg.function}' not found in logic.py. "
                f"Available names: {[n for n in dir(module) if not n.startswith('_')]}"
            )

        # Wrap with static parameters if configured, preserving the full
        # signature (including tool_context) so ADK injects it correctly.
        if cfg.parameters:
            func = _wrap_with_static_params(
                func,
                static=dict(cfg.parameters),
                name=defn.name,
                doc=defn.description,
            )

        return FunctionTool(func=func)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _iter_tool_dirs(tools_dir: Path) -> list[Path]:
        """Return sorted sub-directories of *tools_dir* that contain a tool.yaml."""
        if not tools_dir.is_dir():
            raise FileNotFoundError(
                f"tools_dir not found: {tools_dir}. "
                "Set the correct path when calling load_sync() / load_async()."
            )
        return sorted(
            d for d in tools_dir.iterdir() if d.is_dir() and (d / "tool.yaml").exists()
        )
