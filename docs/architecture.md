# Architecture

> Proto-first, config-driven tool framework for ADK agents.
> Adding a new tool means dropping a folder on disk. Adding a new tool *type*
> means writing one proto + one handler class.

---

## 1. Design Principles

| Principle | Rule |
|-----------|------|
| **Proto-first contracts** | Both the tool's *config* and its *request/response* are `.proto` files — the YAML is only a declarative binding layer. |
| **Two-level schema enforcement** | Level 1: `tool.yaml config:` block is validated against the tool type's config proto at **load time**. Level 2: per-call input/output is validated against `request.proto` / `response.proto` at **call time**. |
| **Zero-code extensibility** | New tool type = one config schema proto + one handler class + one registry call. No core edits. |
| **Typed auth** | A shared `AuthConfig` proto describes bearer / api_key / oauth2 / basic. No free-form credential strings in YAML. |
| **Eager loading** | Every tool is discovered, validated, and compiled once at import. Misconfigurations surface at startup, never at call time. |
| **Direct imports** | `from agent_tools import check_billing` — each tool is an awaitable callable exposing its own ADK/JSON schema. |
| **Env-var runtime tuning** | Global defaults (tools dir, timeout, retries, log level) are all `AGENT_TOOLS_*` env vars. |

---

## 2. High-Level Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Calling code / ADK agent                           │
│  from agent_tools import check_billing                                │
│  await check_billing(customer_id="X", period="2026-04")               │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
                         ToolFunction                    (src/core/function.py)
                     strips _headers kwarg,
                     forwards to runtime.execute
                                │
                                ▼
                          ToolRuntime                    (src/core/runtime.py)
                    ┌───────────┴────────────┐
                    │                        │
              ToolRegistry            MiddlewarePipeline  (src/middleware/pipeline.py)
           (name → ToolDefinition)
                                  AuthMiddleware         ctx.resolved_auth
                                       │
                                  RetryMiddleware        exponential backoff
                                       │
                              ProtoValidationMiddleware  validates input + output
                                       │
                                 LoggingMiddleware       structured logs
                                       │
                                 ExecutorRouter          dispatch by handler_class
                                       │
                              ┌───────────┬──┴─────────┬────────────┐
                              ▼           ▼            ▼            ▼
                         APIHandler  MCPHandler FunctionHandler  CTAHandler

STARTUP PATH (at import):
  ToolLoader → reads every tool.yaml
             → ConfigValidator checks config: against ToolTypeRegistry[type].config_proto
             → ProtoLoader compiles request.proto + response.proto
             → registers ToolDefinition in ToolRegistry
             → ToolFunction(name, runtime) exposed as a module-level attribute
```

---

## 3. Package Layout

`src/` **is** the `agent_tools` package root — sub-packages sit directly inside
it with no extra wrapper folder. `pyproject.toml` maps `"agent_tools" = "src"`.

```
src/
├── __init__.py                 Auto-discovers tools; exposes each as a top-level callable
│
├── core/                       agent_tools.core
│   ├── settings.py             Env-var config (Settings singleton)
│   ├── definition.py           ToolDefinition, ExecutionConfig, ToolTypeEntry
│   ├── registry.py             In-memory tool registry
│   ├── type_registry.py        ToolTypeRegistry — type name → (config proto, handler)
│   ├── config_validator.py     Validates tool.yaml `config:` against type's proto schema
│   ├── loader.py               Scans tools dir, validates YAML, compiles protos
│   ├── runtime.py              ToolRuntime + ExecutionContext
│   ├── function.py             ToolFunction — awaitable wrapper, handles _headers kwarg
│   └── context.py              Request-scoped ContextVar for dynamic header injection
│
├── proto/                      agent_tools.proto
│   ├── loader.py               Compiles .proto via grpc_tools.protoc
│   ├── descriptor.py           ProtoDescriptor — from_dict / to_dict helpers
│   └── converter.py            Derives JSON Schema from proto descriptor (ADK bridge)
│
├── middleware/                 agent_tools.middleware
│   ├── pipeline.py             Builds: Auth → Retry → ProtoValidation → Logging → Router
│   ├── auth.py                 Resolves env-var credentials into ctx.resolved_auth
│   ├── retry.py                Exponential-backoff retry
│   ├── proto_validation.py     Validates input/output against proto schemas
│   └── logging.py              Structured call logging (tool, status, ms)
│
├── handlers/                   agent_tools.handlers
│   ├── base.py                 BaseHandler ABC
│   ├── router.py               ExecutorRouter — dispatches by handler_class
│   ├── api_handler.py          HTTP via httpx; templated + runtime-injected headers
│   ├── mcp_handler.py          MCP protocol client (supports mock_mode)
│   ├── function_handler.py     Loads logic.py, awaits async run(inputs)
│   └── cta_handler.py          Dialogflow CX DetectIntent (supports mock_mode)
│
├── schemas/                    Per-type config schemas (data — no __init__.py)
│   ├── auth_config.proto       Shared AuthConfig + SecretRef source types
│   ├── api_tool_config.proto
│   ├── mcp_tool_config.proto
│   ├── function_tool_config.proto
│   └── cta_tool_config.proto
│
└── tools/                      Your tool definitions (one folder per tool)
    ├── weather_api/            type: api     (real HTTP + templated headers/params)
    ├── docs_mcp/               type: mcp     (mock_mode demo)
    ├── score_function/         type: function (local logic.py)
    └── support_cta/            type: cta     (Dialogflow CX mock_mode demo)
```

---

## 4. Core Components

### ToolLoader — `core/loader.py`
Walks the tools directory, reads every `tool.yaml`, hands the `config:` block to
`ConfigValidator`, compiles `request.proto` / `response.proto` via `ProtoLoader`,
and returns a fully-resolved `ToolDefinition`.

### ConfigValidator — `core/config_validator.py`
Looks up the tool type's config schema in the `ToolTypeRegistry`, parses the
YAML dict through the proto message, and round-trips it back to a cleaned dict.
Any missing required field, unknown field, or wrong-type field fails **here**
with a human-readable error — not at first call.

### ToolTypeRegistry — `core/type_registry.py`
A map of `type_name → (config_proto_path, handler_class)`. The default registry
ships with the four primary types: `api`, `mcp`, `function`, `cta`. Additional types
register themselves via `tr.default_type_registry.register(...)` **before**
`agent_tools` is imported.

### ToolRuntime — `core/runtime.py`
The single execution entry point. Holds the registry, settings, and a built
middleware pipeline. `runtime.execute(name, kwargs)` is what every tool call
ultimately routes through.

### ExecutionContext — `core/runtime.py`
One per call. Carries `tool_def`, `raw_kwargs`, `validated_input`,
`resolved_auth`, `proto_input`, `result`. Middleware mutate it; handlers read it.

### ToolFunction — `core/function.py`
Thin awaitable wrapper. `from agent_tools import my_tool` gives you one of
these. It forwards `kwargs` to `runtime.execute`, peels the reserved `_headers`
kwarg into the request-scoped header context (see §7), and exposes schema
helpers (`.schema`, `.all_schemas()`, `.all_tools()`, `.schemas_for(...)`).

---

## 5. Middleware Pipeline

Built in `middleware/pipeline.py`. Order (outermost first):

| # | Middleware | Responsibility |
|---|------------|---------------|
| 1 | `AuthMiddleware` | Reads `config.auth`, resolves env-var credentials, writes `ctx.resolved_auth` |
| 2 | `RetryMiddleware` | Exponential backoff; retries `RetryableError` up to `settings.default_retries` |
| 3 | `ProtoValidationMiddleware` | Validates `kwargs` against `request.proto` → `ctx.validated_input`; validates result against `response.proto` |
| 4 | `LoggingMiddleware` | Structured before/after logs with timing + status |
| 5 | `ExecutorRouter` | Terminal — dispatches to the handler class recorded on `ToolDefinition` |

Each middleware is a class with a single `wrap(next_fn) -> async fn` method.
Adding one is additive: write the class, append it to `MiddlewarePipeline.build`.

---

## 6. Handlers

All handlers extend `BaseHandler` and implement `async execute(ctx)`. They
receive a fully-populated `ExecutionContext` and return a plain dict (which the
proto-validation middleware then re-checks against `response.proto`).

| Handler | Type  | Transport | Config proto |
|---------|-------|-----------|--------------|
| `APIHandler`    | `api`    | HTTP via httpx — OpenAPI-style call, rich auth, templated params/headers/body | `api_tool_config.proto` |
| `MCPHandler`    | `mcp`    | MCP protocol client. Supports `mock_mode: true` for demos. | `mcp_tool_config.proto` |
| `FunctionHandler` | `function` | Loads `logic.py`, awaits `async run(inputs)`. | `function_tool_config.proto` |
| `CTAHandler`    | `cta`    | Google Dialogflow CX `DetectIntent`. Supports `mock_mode: true`. | `cta_tool_config.proto` |

These four are the only types registered by default. Custom types register
themselves via `ToolTypeRegistry.register(...)` — see §9.

---

## 6a. Authentication — SecretRef sources

Every credential value (`token`, `key`, `client_id`, `client_secret`,
`username`, `password`, `credentials`) is a `SecretRef` that tells the
runtime **where** the value lives:

| `source`      | Resolved by `resolve_auth` |
|---------------|----------------------------|
| `ENV`         | `os.environ[<name>]` — default |
| `HEADER`      | Inbound HTTP header from `with_request_headers(...)` / `_headers=` kwarg. Case-insensitive lookup. |
| `PARAMETER`   | Field on the validated request proto |
| `GCP_SECRET`  | Google Secret Manager resource: `projects/P/secrets/S/versions/V` |

Two higher-level GCP auth types piggy-back on this:

- **`service_account`** — JSON key from any `SecretRef`; `google.oauth2.service_account` mints an access token (or an ID token when `audience` is set).
- **`service_agent`** — Application Default Credentials, optionally impersonating `target_principal` via `google.auth.impersonated_credentials`.

Legacy string fields (`token_env`, `key_env`, `client_id_env`, …) remain
accepted by the proto schema and are up-converted to `{source: ENV, name: …}`
at resolve time, so pre-refactor `tool.yaml` files keep working unchanged.

All auth resolution happens exactly once per call in `AuthMiddleware` —
`ctx.resolved_auth` is then consumed by handlers to inject headers.

---

## 7. Dynamic Header Injection (API tools)

`APIHandler` assembles outgoing headers from three **always-on** sources and
one **opt-in** source:

1. **Static values** from `tool.yaml` `headers:` map.
2. **Templated values** in the same map.
   - `{{field_name}}` → pulls from `ctx.validated_input` (i.e. the request proto).
   - `{{env:VAR_NAME}}` → pulls from `os.environ`.
   - Any header whose template references an unresolved value is **skipped**
     silently — lets you declare optional trace/tenant headers.
3. **Auth headers** injected by `AuthMiddleware` (e.g. `Authorization: Bearer …`).
4. **Runtime-injected headers** from agent code — gated by the tool's
   `runtime_headers` allow-list.

### The `runtime_headers` allow-list

A tool must explicitly declare which header names it accepts from the
runtime context before anything the agent passes via
`with_request_headers(...)` or the `_headers=` kwarg reaches the wire:

```yaml
config:
  runtime_headers:                     # opt-in. Absent/empty ⇒ feature is off.
    - X-Trace-Id
    - X-Tenant-Id
    - Authorization                    # include to allow auth override
```

Comparison is case-insensitive. Any runtime-supplied header whose name is
**not** on the list is silently dropped before the HTTP call is made. This
keeps agent code from accidentally (or maliciously) overriding headers the
tool didn't design for — including auth.

When an allow-listed header is supplied at runtime, it **overrides** the
corresponding yaml-templated or auth-injected value.

### Entry points (on the agent side)

```python
from agent_tools import with_request_headers, weather_api

# Block-scoped — applies to every tool call inside the with-block
with with_request_headers({"X-Trace-Id": trace}):
    await weather_api(city="London", units="metric", trace_id="t-1")

# One-shot via the reserved _headers= kwarg
await weather_api(
    city="Tokyo", units="metric", trace_id="t-2",
    _headers={"X-Trace-Id": trace},
)
```

Implementation:
- Template resolver: `src/handlers/api_handler.py::_render_headers`
- Allow-list filter: `src/handlers/api_handler.py::_filter_runtime_headers`
- Runtime context: `src/core/context.py::with_request_headers`

---

## 8. Startup Sequence

```
import agent_tools
  └─► __init__.py
       ├─► runtime = ToolRuntime.from_env()
       │     ├─► Settings.load()                    # reads AGENT_TOOLS_* env
       │     ├─► ToolLoader.load_all(tools_dir)
       │     │     for each tool folder:
       │     │       ├─► parse tool.yaml
       │     │       ├─► ConfigValidator.validate(config, type_entry)
       │     │       │     └─► proto round-trip — raises on any violation
       │     │       ├─► ProtoLoader.load(request.proto, response.proto)
       │     │       └─► yield ToolDefinition(...)
       │     ├─► ToolRegistry.register(defn) for each
       │     └─► MiddlewarePipeline.build(settings)
       │
       └─► for each registered tool name:
             globals()[name] = ToolFunction(name, runtime)
```

Anything that can fail — bad YAML, unknown tool type, missing proto field,
wrong credential block — fails **here**, at import. Never at call time.

---

## 9. Extending the Framework

### Add a new tool
1. `mkdir src/tools/my_tool`
2. Drop in `tool.yaml`, optional `request.proto` / `response.proto`, optional
   `logic.py` (for `type: python`).
3. Import — it's there.

### Add a new tool *type*
1. Define the config schema at `src/schemas/<type>_tool_config.proto`.
2. Implement the handler at `src/handlers/<type>_handler.py`, extending
   `BaseHandler`.
3. Register it — *before* importing `agent_tools`:
   ```python
   from pathlib import Path
   import agent_tools.core.type_registry as tr
   from my_package.handlers import KafkaHandler

   tr.default_type_registry.register(
       "kafka",
       Path("src/schemas/kafka_tool_config.proto"),
       KafkaHandler,
   )
   import agent_tools
   ```

### Add middleware
Write a class with `wrap(next_fn)` and append it to `MiddlewarePipeline.build`
in `src/middleware/pipeline.py`. Order is outer → inner.

---

## 10. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_TOOLS_DIR` | `src/tools/` (package-relative) | Path to your tools directory |
| `AGENT_TOOLS_TIMEOUT` | `30` | Default HTTP/RPC timeout (seconds) |
| `AGENT_TOOLS_RETRIES` | `3` | Default retry attempts per call |
| `AGENT_TOOLS_LOG_LEVEL` | `INFO` | Python logging level |

Resolved once in `Settings.load()` at startup.

---

## 11. Data Contracts Summary

| Artifact | File | Validated… |
|---|---|---|
| Tool config | `tool.yaml` `config:` block | at load time against `schemas/<type>_tool_config.proto` |
| Auth config | inline under `config.auth` | at load time against `schemas/auth_config.proto` |
| Request input | `request.proto` | at call time by `ProtoValidationMiddleware` |
| Response output | `response.proto` | at call time by `ProtoValidationMiddleware` |
| ADK / LLM schema | derived from `request.proto` | on access via `.schema` / `.all_schemas()` |

Every value the agent hands in, and every value the tool hands back, passes
through a proto round-trip. The YAML is ergonomic sugar; the protos are the
source of truth.
