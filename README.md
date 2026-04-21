# ai-agent-shared-tools

> **Proto-first, config-driven tool framework for ADK agents.**
> Define tools in YAML + `.proto`. Import and call them like plain Python async functions.

```python
from agent_tools import check_billing

result = await check_billing(customer_id="CUST-001", period="2026-04")
```

> Looking for design internals, middleware order, handler contracts, or how
> things wire together? See **[docs/architecture.md](docs/architecture.md)**.

---

## Contents

- [Install](#install)
- [Build & publish on GitHub](#build--publish-on-github)
- [Create your first tool (5 steps)](#create-your-first-tool-5-steps)
- [Tool types](#tool-types)
- [Auth](#auth)
- [Dynamic headers](#dynamic-headers)
- [Use in an ADK agent](#use-in-an-adk-agent)
- [Custom tool type](#custom-tool-type)
- [Environment variables](#environment-variables)
- [Develop](#develop)

---

## Install

```bash
# From PyPI (once published)
pip install ai-agent-shared-tools

# Optional extras
pip install "ai-agent-shared-tools[bigquery]"   # adds google-cloud-bigquery
pip install "ai-agent-shared-tools[mcp]"        # adds mcp client
pip install "ai-agent-shared-tools[all]"        # everything

# Straight from GitHub (no publish step needed)
pip install git+https://github.com/cloudsufi/ai-agent-shared-tools@main
pip install git+https://github.com/cloudsufi/ai-agent-shared-tools@v0.1.0

# From a GitHub Release wheel
pip install https://github.com/cloudsufi/ai-agent-shared-tools/releases/download/v0.1.0/ai_agent_shared_tools-0.1.0-py3-none-any.whl
```

Import path is `agent_tools` (the distribution name only affects `pip install`):

```python
from agent_tools import with_request_headers, check_billing
```

---

## Build & publish on GitHub

### 1. Build the distribution

```bash
pip install build
make clean && python -m build        # → dist/*.whl and dist/*.tar.gz
```

The wheel bundles your `tool.yaml` + `.proto` files — see the
`[tool.setuptools.package-data]` block in `pyproject.toml`.

### 2. Tag a release

```bash
git tag v0.1.0
git push origin v0.1.0
```

### 3. Publish a GitHub Release

```bash
gh release create v0.1.0 dist/*.whl dist/*.tar.gz --generate-notes
```

Consumers install with any of the `pip install …` forms shown above.

### 4. (Optional) Automate releases with GitHub Actions

Add `.github/workflows/release.yml`:

```yaml
name: release
on:
  push:
    tags: ["v*"]
jobs:
  build-release:
    runs-on: ubuntu-latest
    permissions: { contents: write }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install build
      - run: python -m build
      - uses: softprops/action-gh-release@v2
        with: { files: dist/* }
```

Push a tag → wheel + sdist attached to the release automatically.

### 5. (Optional) Publish to GitHub Packages registry

Only if you want private, authenticated installs. Requires a `GITHUB_TOKEN`
with `write:packages`:

```bash
pip install twine
twine upload --repository-url https://pypi.pkg.github.com/cloudsufi dist/*
```

---

## Create your first tool (5 steps)

Build a `check_billing` tool that hits a REST API, validates inputs with proto,
and returns a typed response.

### 1. Folder

Each tool owns a folder inside `src/tools/` (or your custom `AGENT_TOOLS_DIR`):

```
src/tools/check_billing/          ← folder name = tool name
├── tool.yaml
├── request.proto
└── response.proto
```

### 2. `tool.yaml`

```yaml
name:        check_billing          # must match the folder name
version:     "1.0"
type:        api                    # api | rest | python | mcp | grpc | bigquery
description: "Retrieve billing summary for a customer."

config:
  endpoint: "https://api.billing.internal/v1/bills"
  method:   GET

  auth:
    bearer:
      token_env: BILLING_API_KEY    # reads os.environ["BILLING_API_KEY"]

  # URL query params — {{field}} pulls from the request proto at call time
  params:
    customer_id: "{{customer_id}}"
    period:      "{{period}}"

  timeout_seconds: 15
  max_retries:     2

execution:
  timeout: 15
  retries: 2
```

**Key `config` fields by type:**

| Field | Applies to | Description |
|-------|-----------|-------------|
| `endpoint` | api, grpc, mcp | Target URL or host:port |
| `method` | api | HTTP verb: GET, POST, PUT, … |
| `auth` | api, rest, mcp, grpc | Auth block — see [Auth](#auth) |
| `params` | api | URL query params (`{{field}}`, `{{env:VAR}}`) |
| `body_template` | api | JSON body template (`{{field}}`) |
| `headers` | api, rest | Headers map (`{{field}}`, `{{env:VAR}}`) |
| `timeout_seconds` | all | Request timeout |
| `max_retries` | api | Retry count |

### 3. `request.proto`

```proto
syntax = "proto3";
package check_billing;

message CheckBillingRequest {
  string customer_id = 1;   // maps to {{customer_id}}
  string period      = 2;   // maps to {{period}}
}
```

### 4. `response.proto`

```proto
syntax = "proto3";
package check_billing;

message CheckBillingResponse {
  string   customer_id  = 1;
  double   total_amount = 2;
  string   currency     = 3;
  string   status       = 4;
  string   period       = 5;
  repeated LineItem line_items = 6;
}

message LineItem {
  string description = 1;
  double amount      = 2;
  string code        = 3;
}
```

> `request.proto` and `response.proto` are both optional. Omit them if the tool
> doesn't need schema validation.

### 5. Set credentials and call

```bash
export BILLING_API_KEY="sk-your-api-key-here"
```

```python
from agent_tools import check_billing

result = await check_billing(customer_id="CUST-001", period="2026-04")
print(result["total_amount"])   # → 1234.56
```

Tools are discovered, validated, and compiled at **import time**. Any
misconfiguration (bad YAML, unknown field, missing required config) raises
immediately — not at first call.

---

## Tool types

### API tool (HTTP / REST)

```yaml
type: api
config:
  endpoint: "https://api.example.com/v1/resource"
  method:   POST
  headers:
    Content-Type: application/json
  auth:
    bearer:
      token_env: MY_TOKEN
  body_template: '{"id": "{{id}}", "action": "{{action}}"}'
  timeout_seconds: 30
  max_retries: 3
```

`{{placeholder}}` in `params`, `body_template`, and `headers` is filled from
the validated request proto fields at call time. See [Dynamic headers](#dynamic-headers).

### Python tool (custom logic)

```
tools/enrich_lead/
├── tool.yaml
├── request.proto
├── response.proto
└── logic.py           ← must export async run(inputs) -> dict
```

```yaml
type: python
config:
  async_mode: true
  parameters:
    api_url: "https://data.example.com/enrich"   # static params merged into inputs
```

```python
# logic.py
async def run(inputs: dict) -> dict:
    email   = inputs["email"]
    company = inputs["company"]
    # ... your logic ...
    return {"score": 0.92, "industry": "SaaS", "employees": 250}
```

### MCP tool

```yaml
type: mcp
config:
  endpoint: "https://mcp.example.com"
  tool_name: search_documents
  auth:
    bearer:
      token_env: MCP_API_KEY
  timeout_seconds: 20
```

### gRPC tool

```yaml
type: grpc
config:
  endpoint: "grpc.internal:443"
  service_name: BillingService
  method_name:  GetSummary
  use_tls:      true
  auth:
    bearer:
      token_env: GRPC_TOKEN
  timeout_seconds: 10
```

### BigQuery tool

Requires `pip install "ai-agent-shared-tools[bigquery]"`.

```yaml
type: bigquery
config:
  project: my-gcp-project
  dataset: analytics
  query:   "SELECT * FROM analytics.events WHERE user_id = @user_id LIMIT 100"
  max_results: 100
```

### OpenAPI / REST spec tool

Loads an OpenAPI spec and resolves the operation by `operationId`.

```yaml
type: rest
config:
  spec_url:     "https://api.example.com/openapi.json"   # or spec_file: ./openapi.yaml
  operation_id: listOrders
  auth:
    api_key:
      header_name: X-Api-Key
      key_env:     MY_API_KEY
  timeout_seconds: 15
```

---

## Auth

Credentials come from env vars — never from `tool.yaml`.

```yaml
config:
  auth:
    # 1. Bearer token
    bearer:
      token_env: MY_API_TOKEN       # → Authorization: Bearer <value>

    # 2. API key header
    api_key:
      header_name: X-Api-Key
      key_env:     MY_API_KEY       # → X-Api-Key: <value>

    # 3. OAuth 2.0 client credentials
    oauth2:
      client_id_env:     OAUTH_CLIENT_ID
      client_secret_env: OAUTH_CLIENT_SECRET
      token_url:         "https://auth.example.com/token"
      scope:             "read write"

    # 4. HTTP Basic
    basic:
      username_env: MY_USERNAME
      password_env: MY_PASSWORD
```

---

## Dynamic headers

Three ways to get a header onto an outgoing request — combinable, with clear
precedence.

### 1. Static or templated in `tool.yaml`

```yaml
config:
  headers:
    Accept:        application/json
    X-Tenant-Id:   "{{tenant_id}}"        # from request proto field
    X-App-Context: "{{env:APP_CONTEXT}}"  # from process env var
```

- `{{field}}` → pulls from the validated request input.
- `{{env:VAR}}` → pulls from `os.environ`.
- A header is **silently skipped** if any of its tokens is missing — declare
  optional trace/tenant headers safely.

### 2. Env vars set on the agent side

Set the env var anywhere before the process starts (shell, systemd, k8s, `.env`):

```bash
export APP_CONTEXT=prod
```

The `{{env:APP_CONTEXT}}` token above picks it up.

### 3. Runtime injection from agent code

Two equivalent entry points:

```python
from agent_tools import with_request_headers, check_billing

# Block-scoped — applies to every tool call inside
with with_request_headers({"X-Trace-Id": trace, "X-Tenant-Id": tenant}):
    await check_billing(customer_id="CUST-001", period="2026-04")

# One-shot via the reserved _headers kwarg
await check_billing(
    customer_id="CUST-001",
    period="2026-04",
    _headers={"X-Trace-Id": trace},
)
```

### Precedence (last wins)

1. `tool.yaml` headers (after template resolution)
2. Auth headers injected by `AuthMiddleware`
3. `with_request_headers(...)` / `_headers=` — **highest**

Runtime headers override auth too — useful for testing or impersonation.

---

## Use in an ADK agent

Every imported tool carries `.runtime`, `.schema`, `.all_schemas()`, and
`.all_tools()` — no separate runtime import needed.

```python
from agent_tools import check_billing, enrich_lead
from google.adk.agents import LlmAgent

# Single tool
agent = LlmAgent(
    model        = "gemini-2.0-flash",
    tools        = [check_billing],
    tool_schemas = [check_billing.schema],   # JSON Schema derived from request.proto
)

# All registered tools at once
agent = LlmAgent(
    model        = "gemini-2.0-flash",
    tools        = check_billing.all_tools(),
    tool_schemas = check_billing.all_schemas(),
)

# Subset of tools
agent = LlmAgent(
    model        = "gemini-2.0-flash",
    tools        = check_billing.schemas_for("check_billing", "enrich_lead"),
)

# Direct call (works outside an agent too)
result = await check_billing(customer_id="CUST-001", period="2026-04")
```

### What `.schema` looks like

```python
check_billing.schema
# {
#   "name": "check_billing",
#   "description": "Retrieve billing summary for a customer.",
#   "parameters": {
#     "type": "object",
#     "properties": {
#       "customer_id": {"type": "string"},
#       "period":      {"type": "string"}
#     },
#     "required": ["customer_id", "period"]
#   }
# }
```

---

## Custom tool type

Three files. No changes to core.

**1. Config schema** (`src/schemas/kafka_tool_config.proto`):

```proto
syntax = "proto3";
package agent_tools;
import "auth_config.proto";

message KafkaToolConfig {
  string     bootstrap_servers = 1;
  string     topic             = 2;
  AuthConfig auth              = 3;
  int32      timeout_seconds   = 4;
}
```

**2. Handler** (`src/handlers/kafka_handler.py`):

```python
from agent_tools.handlers.base import BaseHandler

class KafkaHandler(BaseHandler):
    async def execute(self, ctx):
        cfg = ctx.tool_def.config
        # ... produce/consume from Kafka ...
        return {"status": "ok"}
```

**3. Register — before importing `agent_tools`:**

```python
from pathlib import Path
import agent_tools.core.type_registry as tr
from agent_tools.handlers.kafka_handler import KafkaHandler

tr.default_type_registry.register(
    "kafka",
    Path("src/schemas/kafka_tool_config.proto"),
    KafkaHandler,
)

import agent_tools   # now type: kafka is recognised
```

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_TOOLS_DIR` | `src/tools/` (package-relative) | Path to your tools directory |
| `AGENT_TOOLS_TIMEOUT` | `30` | Default HTTP/RPC timeout in seconds |
| `AGENT_TOOLS_RETRIES` | `3` | Default retry attempts per call |
| `AGENT_TOOLS_LOG_LEVEL` | `INFO` | Python logging level |

```bash
export AGENT_TOOLS_DIR="/path/to/my/tools"
export AGENT_TOOLS_TIMEOUT=60
export AGENT_TOOLS_RETRIES=5
export AGENT_TOOLS_LOG_LEVEL=DEBUG
```

---

## Develop

```bash
make install        # pip install -e ".[dev]"
make test           # full test suite
make test-cov       # with coverage report
make lint           # ruff check + format
make typecheck      # mypy
make check          # lint + typecheck + test
make build          # python -m build
make clean          # remove build artefacts
```

Package layout, middleware order, handler contracts, startup sequence →
**[docs/architecture.md](docs/architecture.md)**.

---

## License

MIT © CloudSufi
