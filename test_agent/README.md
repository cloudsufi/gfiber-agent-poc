# test_agent — Interactive ADK Agent

An interactive web UI powered by Google ADK that gives natural language access
to all registered `agent_tools`. Every tool is automatically discoverable and
callable via chat prompts.

## Features

- **Auto-discovery**: Tools from `agent_tools` appear immediately in the UI.
- **Natural language**: Describe what you want in plain English; the LLM picks the right tool.
- **Session tracking**: Each conversation maintains session_id, user context, and structured logs.
- **Zero boilerplate**: The `adk web` command handles FastAPI, WebSockets, and the UI.

## Quick Start

### 1. Set up your API keys

Copy the env template and fill in your keys:

```bash
cp test_agent/.env.example test_agent/.env
# edit .env with your actual API keys
```

Required:
- `GOOGLE_API_KEY` — your Gemini API key

Optional (for specific tools):
- `WEATHER_API_KEY` — for the weather_api tool
- `GFIBER_API_KEY` — for the get_customer_details tool
- `GFIBER_API_BASE_URL` — override the API server URL

### 2. Launch the web UI

```bash
# Load env vars and start the server
set -a && source test_agent/.env && set +a
adk web test_agent
```

The server opens at **http://127.0.0.1:8000**.

### 3. Start chatting

Type any prompt:
- _"What is the weather in London?"_ → calls `weather_api`
- _"Score this lead: email=alice@example.com, company=Acme, spend=50000, region=us-west"_ → calls `score_function`
- _"Search for onboarding"_ → calls `docs_mcp`

## Files

| File | Purpose |
|---|---|
| [agent.py](agent.py) | Builds the `root_agent` that ADK discovers and serves. |
| [.env.example](.env.example) | Template for API keys (copy to `.env` and fill in). |
| [requirements.txt](requirements.txt) | Runtime dependencies. |

## Add Your Own Tool

1. Create a folder: `src/tools/<your_tool>/`
2. Add `tool.yaml` (+ optional `input.yaml`, `output.yaml`, `logic.py`)
3. The tool is automatically registered and appears in the web UI on next startup

No changes to `agent.py` needed.

## Custom Tools Directory

To use tools from a different location:

```bash
export AGENT_TOOLS_DIR=/path/to/your/tools
set -a && source test_agent/.env && set +a
adk web test_agent
```
