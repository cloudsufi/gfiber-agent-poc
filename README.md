# ai-agent-shared-tools

> **YAML-first, config-driven tool framework for ADK agents.**
> Every tool is a folder on disk: `tool.yaml` for configuration,
> `input.yaml` / `output.yaml` for JSON-Schema validation of inputs /
> outputs. Import and call each tool like an ordinary async function.

```python
from agent_tools import weather_api

result = await weather_api(city="London", units="metric", trace_id="t-1")
```

> Design internals, middleware order, handler contracts → **[docs/architecture.md](docs/architecture.md)**

---

## Contents

- [Install](#install)
- [Build & publish on GitHub](#build--publish-on-github)
- [Four tool types](#four-tool-types)
- [Authoring a tool](#authoring-a-tool)
- [Authentication](#authentication)
- [Dynamic headers](#dynamic-headers)
- [Use in an ADK agent](#use-in-an-adk-agent)
- [Environment variables](#environment-variables)
- [Develop](#develop)

---

## Install

```bash
pip install ai-agent-shared-tools

# Optional extras
pip install "ai-agent-shared-tools[mcp]"   # MCP client
pip install "ai-agent-shared-tools[gcp]"   # google-auth + Secret Manager + Dialogflow CX
pip install "ai-agent-shared-tools[all]"   # everything

# Directly from GitHub — no publish step required
pip install git+https://github.com/cloudsufi/gfiber-agent-poc@main
```

Import path is always `agent_tools` (the distribution name only affects `pip`):

```python
from agent_tools import weather_api, docs_mcp, score_function, support_cta
```

---

## Build & publish on GitHub

```bash
# 1. Build wheel + sdist
pip install build
make clean && python -m build      # → dist/*.whl, dist/*.tar.gz

# 2. Tag
git tag v0.2.0 && git push origin v0.2.0

# 3. Publish a Release (attaches artifacts)
gh release create v0.2.0 dist/*.whl dist/*.tar.gz --generate-notes
```

Consumers can then `pip install https://github.com/…/releases/download/v0.2.0/…whl`
or `pip install git+https://github.com/…@v0.2.0`. For a `on: push: tags` GitHub
Actions workflow template see [docs/architecture.md#packaging--releases](docs/architecture.md#packaging--releases).

---

## Four tool types

| Type | Handler | When to use | Config schema |
|------|---------|-------------|---------------|
| `api`    | HTTP via httpx | OpenAPI-style call to any REST service | [api_tool_config.yaml](src/schema/types/api_tool_config.yaml) |
| `mcp`    | MCP client | Delegates to an MCP server's named tool | [mcp_tool_config.yaml](src/schema/types/mcp_tool_config.yaml) |
| `function` | Runs `logic.py` | Anything that's pure Python logic | [function_tool_config.yaml](src/schema/types/function_tool_config.yaml) |
| `cta`    | Dialogflow CX | Route an utterance through a Google conversational agent | [cta_tool_config.yaml](src/schema/types/cta_tool_config.yaml) |

`mcp` and `cta` both support `mock_mode: true` — returns a deterministic stub
so you can develop and demo without a running MCP server or CX agent.

These four are the only types registered by default. Adding a new type means
three steps and zero edits to framework code — see [docs/architecture.md §9](docs/architecture.md#9-extending-the-framework).

---

## Authoring a tool

Every tool is a directory under `src/tools/<tool_name>/`:

```
src/tools/weather_api/
├── tool.yaml         # config — validated against the type's YAML schema at load time
├── input.yaml        # JSON Schema for kwargs — validates at call time
└── output.yaml       # JSON Schema for handler result — validates at call time
```

A fourth file, `logic.py`, is required only for `type: function`.

### Example — `type: api`

```yaml
# src/tools/weather_api/tool.yaml
name:        weather_api
version:     "1.0"
type:        api
description: "Return current weather for a city."

input_schema:  input.yaml
output_schema: output.yaml

config:
  endpoint: "https://api.example.com/v1/weather"
  method:   GET

  headers:
    Accept:      application/json
    X-Agent-Env: "{{env:AGENT_ENV}}"      # optional — skipped when env var unset
    X-Trace-Id:  "{{trace_id}}"           # from request field

  params:
    city:  "{{city}}"
    units: "{{units}}"

  auth:
    bearer:
      token_env: WEATHER_API_KEY          # legacy shorthand — still works

  timeout_seconds: 10
  max_retries:     1

execution:
  retries: 1
  timeout: 10
```

```yaml
# input.yaml
type: object
additionalProperties: false
required: [city, units, trace_id]
properties:
  city:     { type: string }
  units:    { type: string, enum: [metric, imperial] }
  trace_id: { type: string }
```

Import and call:

```python
from agent_tools import weather_api
result = await weather_api(city="London", units="metric", trace_id="t-1")
```

### Example — `type: function`

```yaml
name:        score_function
type:        function
description: "Score a lead using local business rules."
input_schema:  input.yaml
output_schema: output.yaml

config:
  parameters:                         # static values merged into run() inputs
    model_version: "v2.3"
    threshold:     "0.60"
  async_mode: true
```

```python
# logic.py — MUST export async run(inputs: dict) -> dict
async def run(inputs: dict) -> dict:
    score = 0.3 + 0.35 * (inputs["annual_spend"] >= 50_000)
    return {"email": inputs["email"], "score": round(score, 2)}
```

### Example — `type: cta`

```yaml
name:        support_cta
type:        cta
description: "Route a query to the support Dialogflow CX agent."
input_schema:  input.yaml
output_schema: output.yaml

config:
  project_id:       my-gcp-project
  location:         us-central1
  agent_id:         00000000-0000-0000-0000-000000000000
  language_code:    en
  text_field:       text
  session_id_field: session_id

  mock_mode: true        # flip to false in production
  # auth:
  #   service_agent:
  #     scopes: ["https://www.googleapis.com/auth/cloud-platform"]

  timeout_seconds: 20
```

### Example — `type: mcp`

```yaml
name:        docs_mcp
type:        mcp
description: "Search internal documentation via an MCP server."

config:
  endpoint:  "https://mcp.example.internal"
  tool_name: search_documents
  auth:
    bearer:
      token_env: MCP_API_KEY
  mock_mode: true
  timeout_seconds: 20
```

---

## Authentication

Credentials never live in `tool.yaml`. Every credential value is a `SecretRef`
that names its source:

| Source      | Meaning                                            |
|-------------|----------------------------------------------------|
| `ENV`       | `os.environ[<name>]` — default                    |
| `HEADER`    | Inbound HTTP header (caller-supplied, per-call)    |
| `PARAMETER` | Field on the validated request input               |
| `GCP_SECRET`| Google Secret Manager resource name                |

### Auth types

```yaml
config:
  auth:
    # 1. Bearer token
    bearer:
      token:
        source: ENV
        name:   MY_API_TOKEN
    # (legacy shorthand still works:)
    # bearer: { token_env: MY_API_TOKEN }

    # 2. API key header
    api_key:
      header_name: X-Api-Key
      key: { source: ENV, name: MY_API_KEY }

    # 3. OAuth 2.0 client credentials
    oauth2:
      client_id:     { source: ENV, name: OAUTH_CLIENT_ID }
      client_secret: { source: GCP_SECRET, name: "projects/P/secrets/oauth-secret/versions/latest" }
      token_url:     "https://auth.example.com/token"
      scope:         "read write"

    # 4. HTTP Basic
    basic:
      username: { source: ENV, name: MY_USERNAME }
      password: { source: ENV, name: MY_PASSWORD }

    # 5. GCP service account (JSON key → OAuth2 access or ID token)
    service_account:
      credentials: { source: GCP_SECRET, name: "projects/P/secrets/sa-json/versions/latest" }
      scopes: ["https://www.googleapis.com/auth/cloud-platform"]
      # audience: "https://my-cloud-run-service.run.app"    # to mint an ID token instead

    # 6. GCP service agent (Application Default Credentials, optional impersonation)
    service_agent:
      target_principal: svc-agent@my-project.iam.gserviceaccount.com
      scopes: ["https://www.googleapis.com/auth/cloud-platform"]
```

Credentials are resolved once per call in `AuthMiddleware`, exposed on
`ctx.resolved_auth`, and injected as headers by the relevant handler. Headers
that need a caller-supplied value (like a user JWT) can pull from `HEADER`
via the dynamic-headers mechanism below.

---

## Dynamic headers

Headers applied to an outgoing API request come from three sources (last wins):

1. Static `headers:` from `tool.yaml`
2. Templated values in the same map:
   - `{{field}}` — validated request field
   - `{{env:VAR}}` — process env (header is silently skipped if var is unset)
3. Auth headers injected by `AuthMiddleware`

A fourth source — **per-call runtime headers from agent code** — is **opt-in
per tool**. The tool must declare an allow-list in `tool.yaml`:

```yaml
config:
  runtime_headers:         # explicit opt-in. Absent/empty ⇒ feature is off.
    - X-Trace-Id
    - X-Tenant-Id
    - Authorization        # include here to let agent code override auth
```

Without that block, anything the agent passes via `with_request_headers(...)`
or the `_headers=` kwarg is **silently dropped** before the request is sent.
With the block in place, only names that match (case-insensitive) reach the
wire — everything else is filtered out.

```python
from agent_tools import with_request_headers, weather_api

# weather_api declares runtime_headers: [X-Trace-Id].
# X-Trace-Id overrides the yaml-templated value. X-Secret is dropped.
with with_request_headers(
    {"X-Trace-Id": trace, "X-Secret": "would-be-dropped"}
):
    await weather_api(city="London", units="metric", trace_id="t-1")

# One-shot via the reserved _headers= kwarg — same allow-list rules apply.
await weather_api(
    city="Tokyo",
    units="metric",
    trace_id="tool-trace",
    _headers={"X-Trace-Id": "runtime-wins"},
)
```

Declaring `Authorization` in `runtime_headers` is how you let agent code
override the auth-injected token — useful for testing / impersonation, and
explicit so it can't happen accidentally.

---

## Use in an ADK agent

Every imported tool carries `.schema`, `.all_schemas()`, `.all_tools()`,
`.runtime`. The demo agent wraps each in a `BaseTool` adapter so the ADK
`LlmAgent` can consume them directly:

```python
# test_agent/agent.py
from agent_tools import weather_api

def build_agent():
    from google.adk.agents import LlmAgent
    tools = [AgentToolsAdapter(tf) for tf in weather_api.all_tools()]
    return LlmAgent(
        model="gemini-2.0-flash",
        name="demo_agent",
        tools=tools,
    )
```

See [test_agent/](test_agent/) for the full working adapter + runnable demo.

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_TOOLS_DIR`       | `src/tools/` (package-relative) | Path to your tools directory |
| `AGENT_TOOLS_TIMEOUT`   | `30` | Default HTTP/RPC timeout (seconds) |
| `AGENT_TOOLS_RETRIES`   | `3`  | Default retry attempts per call |
| `AGENT_TOOLS_LOG_LEVEL` | `INFO` | Python logging level |

---

## Develop

```bash
make install        # pip install -e ".[dev]"
make test           # pytest — 142 tests cover core + handlers + middleware + schema
make test-cov       # with coverage report
make lint           # ruff check + format
make typecheck      # mypy
make check          # lint + typecheck + test
make build          # python -m build
```

Run the demo against the four sample tools:

```bash
python test_agent/demo.py            # sections 1-7 (no ADK needed)
python test_agent/demo.py --adk      # + ADK LlmAgent (needs google-adk)
```

---

## License

MIT © CloudSufi
