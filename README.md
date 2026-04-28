# adk-tools

YAML-driven, config-validated tool loader for [Google ADK](https://github.com/google/adk-python) agents.

Define tools in simple YAML files. Config is validated at startup — broken configs never silently survive to call time.

## Installation

```bash
# Core (OpenAPI + Function tools)
pip install adk-tools

# With MCP tool support
pip install "adk-tools[mcp]"

# With GCP auth (service_account + Secret Manager)
pip install "adk-tools[gcp]"

# Everything
pip install "adk-tools[all]"
```

Install from source (during development):

```bash
git clone https://github.com/cloudsufi/adk-tools
cd adk-tools
pip install -e ".[all,dev]"
```

---

## Two ways to define tools

### 1. YAML config (directory-based)

One sub-folder per tool, each with a `tool.yaml`:

```
tools/
  weather_api/
    tool.yaml       ← type: openapi, auth, timeout, …
    openapi.yaml    ← OpenAPI 3.x spec
    input.yaml      ← optional JSON Schema (validated at load time)
    output.yaml     ← optional JSON Schema

  docs_mcp/
    tool.yaml       ← type: mcp, server_url or command

  score_function/
    tool.yaml       ← type: function, static parameters
    logic.py        ← async def run(…, tool_context: ToolContext) -> dict
```

Load and pass to an ADK agent:

```python
from adk_tools import load_tools
from google.adk.agents import LlmAgent

tools = load_tools("tools/")          # validated at startup
agent = LlmAgent(model="gemini-2.0-flash", tools=tools, ...)
```

For MCP tools (async connection handshake required):

```python
from adk_tools import load_tools_async

tools, exit_stack = await load_tools_async("tools/")
async with exit_stack:
    agent = LlmAgent(..., tools=tools)
    # run agent here
```

### 2. `@function_tool` decorator

Decorate any function and it is registered automatically:

```python
# my_tools.py
from adk_tools import function_tool
from google.adk.tools.tool_context import ToolContext

@function_tool
async def greet_user(name: str, tool_context: ToolContext) -> str:
    """Greet a user by name."""
    sid = tool_context.state.get("session_id", "?")
    return f"Hello {name}! (session {sid})"

@function_tool
def compute_tax(amount: float, rate: float = 0.1) -> float:
    """Compute tax for an amount."""
    return round(amount * rate, 2)
```

```python
# agent.py
import my_tools                        # triggers @function_tool registrations
from adk_tools import load_tools

tools = load_tools("tools/")           # YAML tools + @function_tool tools merged
agent = LlmAgent(..., tools=tools)
```

---

## Tool types

### `type: openapi`

Wraps `google.adk.tools.openapi_tool.OpenAPIToolset`. Every operation in the spec becomes a separate ADK tool.

```yaml
# tool.yaml
name: weather_api
description: Fetch weather forecasts.
config:
  type: openapi
  spec_file: openapi.yaml
  auth:
    type: bearer
    token_env: WEATHER_API_TOKEN
  timeout_seconds: 15
```

### `type: mcp`

Wraps `google.adk.tools.mcp_tool.MCPToolset`. Supports SSE (HTTP) and stdio transports.

```yaml
config:
  type: mcp
  server_url: https://mcp.example.com/sse     # SSE transport
  tool_filter: [search_docs, get_doc]          # expose only these tools
  auth:
    type: bearer
    token_secret: projects/p/secrets/mcp-token/versions/latest  # from GCP Secret Manager
```

```yaml
config:
  type: mcp
  command: python                              # stdio transport
  args: [-m, my_mcp_server]
  env_vars:
    LOG_LEVEL: info
```

### `type: function`

Wraps `google.adk.tools.FunctionTool` around `logic.py`. Use `tool_context: ToolContext` for session state access.

```yaml
config:
  type: function
  function: run           # default; name of async def in logic.py
  parameters:
    model_version: v2.3   # static kwargs — hidden from LLM schema, injected at call time
    threshold: "0.60"
```

```python
# logic.py
from google.adk.tools.tool_context import ToolContext

async def run(
    company_size: str,
    industry: str,
    tool_context: ToolContext,      # ADK injects this; not in LLM schema
    model_version: str = "v2.3",    # injected from tool.yaml config.parameters
) -> dict:
    """Score a sales lead."""
    session_id = tool_context.state.get("session_id", "")
    ...
```

---

## Auth

Supported auth types for `openapi` and `mcp` tools:

| type | Fields | Source |
|------|--------|--------|
| `bearer` | `token_env` \| `token_secret` | env var or GCP Secret Manager |
| `api_key` | `key_env` \| `key_secret`, `header_name`, `location` | env var or GCP Secret Manager |
| `oauth2` | `client_id_env/secret`, `client_secret_env/secret`, `token_url` | env var or GCP Secret Manager |
| `service_account` | `key_env` \| `key_secret`, `scopes`, `audience` | env var (SA JSON) or GCP Secret Manager |

Read a credential from GCP Secret Manager instead of an env var:

```yaml
auth:
  type: bearer
  token_secret: projects/my-project/secrets/api-token/versions/latest
```

Requires: `pip install "adk-tools[gcp]"`

---

## Config validation

All `tool.yaml` configs are validated by Pydantic at startup:

- Unknown keys are **rejected** (`extra = "forbid"`)
- Required fields are enforced
- `input.yaml` / `output.yaml` are meta-validated as JSON Schema Draft-7 (requires `pip install "adk-tools[validation]"`)
- Missing referenced files (`openapi.yaml`, `logic.py`) raise `FileNotFoundError` immediately

---

## Requirements

- Python ≥ 3.10
- `google-adk >= 0.4`
- `pydantic >= 2.5`
- `pyyaml >= 6.0`
