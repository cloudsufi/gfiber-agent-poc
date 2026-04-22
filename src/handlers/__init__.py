"""
agent_tools.handlers — per-type execution strategies.

A handler is the strategy that actually invokes a tool. The framework
routes to it through :class:`~agent_tools.handlers.router.ExecutorRouter`,
which is the terminal middleware in the pipeline — by the time a handler
runs, auth has been resolved, input has been validated against
``request.proto``, and retries are already wrapping the call.

Each primary tool type has one handler:

===========  ============================  =====================================
Tool ``type`` Handler                        What it does
===========  ============================  =====================================
``api``      ``APIHandler``                HTTP call via httpx; merges static +
                                           templated + allow-listed runtime
                                           headers; resolves auth from the
                                           middleware-supplied credential.
``mcp``      ``MCPHandler``                Calls a named tool on an MCP server.
                                           Supports ``mock_mode`` for demos.
``function`` ``FunctionHandler``           Loads ``logic.py`` from the tool dir
                                           and awaits ``async run(inputs)``.
``cta``      ``CTAHandler``                Dialogflow CX DetectIntent call.
                                           Supports ``mock_mode`` for demos.
===========  ============================  =====================================

All handlers subclass :class:`~agent_tools.handlers.base.BaseHandler` and
implement a single coroutine::

    async def execute(self, ctx: ExecutionContext) -> Any: ...

Extending
---------
Adding a new handler is three files, zero edits to the framework:

1. Define a ``.proto`` config schema for the new type under ``src/schemas/``.
2. Write the handler class subclassing :class:`BaseHandler`.
3. Register with ``default_type_registry.register(name, proto_path, HandlerCls)``
   **before** ``import agent_tools`` so the loader sees the new type.
"""
