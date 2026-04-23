# test_agent — demo agent using `ai-agent-shared-tools`

A minimal runnable demo that exercises the framework end-to-end:

- Tools are auto-discovered from the `agent_tools` package on import.
- Each tool exposes its own JSON schema for LLM tool declarations.
- Tools are awaitable like plain Python async functions.
- Dynamic headers can be injected from the agent side (block-scoped or per-call).
- An optional ADK `LlmAgent` is wired to every registered tool.

## Files

| File | Purpose |
|---|---|
| [agent.py](agent.py) | Builds a `google.adk.agents.LlmAgent` from every registered tool. Import deferred so the module loads without ADK. |
| [demo.py](demo.py) | Runnable script — schemas, direct calls, dynamic headers, optional ADK section. |
| [requirements.txt](requirements.txt) | Runtime deps. |

## Run

From the repo root:

```bash
# 1. Install the framework in editable mode
pip install -e .

# 2. Run the demo (sections 1–4, no ADK needed)
python test_agent/demo.py

# 3. Full demo including the ADK LlmAgent
pip install google-adk
python test_agent/demo.py --adk
```

## Use your own tool

Drop a folder into `src/tools/<your_tool>/` with a `tool.yaml` (+ optional
`input.yaml` / `output.yaml` / `logic.py`). Re-run `python
test_agent/demo.py` — your tool appears in `all_tools()` and `all_schemas()`
automatically. No code changes to `agent.py` or `demo.py` needed.

## Pointing to a different tools directory

```bash
export AGENT_TOOLS_DIR=/path/to/your/tools
python test_agent/demo.py
```
