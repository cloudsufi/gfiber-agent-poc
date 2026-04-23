"""
agent_tools.core — framework nucleus.

This subpackage owns everything that happens between "the framework imports"
and "a tool is ready to be called"::

    Settings.load()              ← env-var config
    ToolTypeRegistry             ← {type name → (config schema path, handler class)}
    ToolLoader.load_all()        ← scan tools/ dir
      ├─ reads tool.yaml
      ├─ ConfigValidator         ← validates config: block
      └─ SchemaLoader            ← loads input/output.yaml
    ToolRegistry.register()      ← {tool name → ToolDefinition}
    ToolRuntime(registry, …)     ← builds MiddlewarePipeline
    ToolFunction(name, runtime)  ← awaitable callable per tool

Public surface
--------------
* :class:`~agent_tools.core.runtime.ToolRuntime` — the one execute entry point.
* :class:`~agent_tools.core.function.ToolFunction` — the awaitable wrapper
  every tool-name import resolves to.
* :class:`~agent_tools.core.definition.ToolDefinition` — the frozen shape of a
  validated tool, with its input/output schemas attached.
* :class:`~agent_tools.core.type_registry.ToolTypeRegistry` — registration API
  for adding new tool types without modifying framework code.
* :class:`~agent_tools.core.context.with_request_headers` — opt-in dynamic
  headers for API tools that declare ``runtime_headers`` in their yaml.

Core imports handlers/middleware only through the type registry and the
pipeline builder, so new handlers / middleware can be added in sibling
subpackages without editing anything here.
"""
