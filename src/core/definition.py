"""
Core data-classes that describe a tool's fully-resolved contract.

Three dataclasses live here; together they are the "loaded form" of a
tool — everything the runtime needs to dispatch a call without re-reading
the tool.yaml / schema files from disk.

* :class:`ExecutionConfig` — per-tool retry / timeout overrides with sentinel
  values that resolve to the global :class:`Settings` defaults at call time.
* :class:`ToolTypeEntry` — what the type registry stores for each type name:
  a path to the config schema YAML and a handler class.
* :class:`ToolDefinition` — the big one. One instance per registered tool,
  produced by :class:`~agent_tools.core.loader.ToolLoader` after schema
  validation passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_tools.core.settings import Settings


@dataclass
class ExecutionConfig:
    """
    Per-tool retry / timeout overrides.

    ``-1`` is the sentinel meaning "use the :class:`Settings` default".
    Call :meth:`resolved` to fill sentinels before executing.
    """

    retries: int = -1
    timeout: int = -1

    def resolved(self, settings: Settings) -> ExecutionConfig:
        """Return a new :class:`ExecutionConfig` with sentinels replaced."""
        return ExecutionConfig(
            retries=self.retries if self.retries >= 0 else settings.default_retries,
            timeout=self.timeout if self.timeout >= 0 else settings.default_timeout,
        )


@dataclass
class ToolTypeEntry:
    """Associates a tool type name with its config schema path and handler class."""

    name: str
    config_schema_path: Path
    handler_class: Any  # type: ignore[misc]


@dataclass
class ToolDefinition:
    """
    Fully-resolved, config-validated description of a single tool.

    Created by :class:`~agent_tools.core.loader.ToolLoader` at startup. Once
    a ``ToolDefinition`` exists, the tool is guaranteed callable — its
    config has been validated against the type's YAML schema, and its
    request/response schemas (if present) have been loaded.

    Fields
    ------
    name
        Matches the tool-directory name. This is what agents import
        (``from agent_tools import <name>``).
    version, type, description
        Copied from ``tool.yaml``. ``type`` must correspond to an entry
        in :class:`ToolTypeRegistry`.
    config
        The YAML ``config:`` block **after** schema validation — unknown
        keys have been rejected, required fields verified, types enforced.
    execution
        Per-tool retry / timeout overrides. See :class:`ExecutionConfig`.
    handler_class
        The :class:`BaseHandler` subclass that will execute this tool. The
        router instantiates it lazily on first use and caches the instance.
    input_schema / output_schema
        Parsed JSON Schema dicts, or ``None`` if the tool didn't ship a
        ``request.yaml`` / ``response.yaml``. Used by
        :class:`SchemaValidationMiddleware` to enforce the contract at
        call time.
    tool_dir
        Filesystem path to the tool's directory. Used by handlers that
        need to load sibling files (e.g. ``FunctionHandler`` loading
        ``logic.py``).
    """

    name: str
    version: str
    type: str
    description: str
    config: dict[str, Any]
    execution: ExecutionConfig
    handler_class: Any  # type: ignore[misc]
    input_schema: dict[str, Any] | None = field(default=None, repr=False)
    output_schema: dict[str, Any] | None = field(default=None, repr=False)
    tool_dir: Path | None = None

    @property
    def adk_schema(self) -> dict[str, Any]:
        """
        Return the JSON-Schema dict required by ADK / LLM framework tool
        declarations.

        Shape::

            {
                "name":        <tool name>,
                "description": <from tool.yaml>,
                "parameters":  <JSON Schema derived from request.yaml>,
            }

        The ``parameters`` block is the tool's ``input_schema`` with
        framework-internal metadata (``$schema``, ``title``) stripped so
        it can be attached directly to an ADK ``FunctionDeclaration``.
        If the tool didn't declare a request schema, ``parameters`` is an
        empty object.
        """
        from agent_tools.schema.converter import to_llm_schema

        return {
            "name": self.name,
            "description": self.description,
            "parameters": to_llm_schema(self.input_schema),
        }
