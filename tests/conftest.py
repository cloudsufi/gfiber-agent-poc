"""Shared pytest fixtures for the agent_tools test suite."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

# ── Fixture helpers ───────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_tools_dir(tmp_path: Path) -> Path:
    """Return an empty temporary directory suitable for use as tools_dir."""
    return tmp_path / "tools"


@pytest.fixture()
def sample_api_tool_dir(tmp_path: Path) -> Path:
    """
    Create a minimal valid API tool directory with tool.yaml and proto files.
    Returns the tool directory path.
    """
    tool_dir = tmp_path / "tools" / "sample_tool"
    tool_dir.mkdir(parents=True)

    (tool_dir / "tool.yaml").write_text(
        yaml.dump({
            "name": "sample_tool",
            "version": "1.0",
            "type": "api",
            "description": "A sample API tool for testing.",
            "config": {
                "endpoint": "https://api.example.com/v1/test",
                "method": "GET",
                "auth": {"bearer": {"token_env": "TEST_API_KEY"}},
                "params": {"id": "{{id}}"},
                "timeout_seconds": 5,
                "max_retries": 1,
            },
            "execution": {"retries": 1, "timeout": 5},
        })
    )
    # Minimal request proto
    (tool_dir / "request.proto").write_text(
        'syntax = "proto3";\nmessage SampleRequest { string id = 1; }\n'
    )
    # Minimal response proto
    (tool_dir / "response.proto").write_text(
        'syntax = "proto3";\nmessage SampleResponse { string result = 1; }\n'
    )
    return tool_dir


@pytest.fixture()
def sample_function_tool_dir(tmp_path: Path) -> Path:
    """Create a minimal valid ``type: function`` tool directory."""
    tool_dir = tmp_path / "tools" / "function_tool"
    tool_dir.mkdir(parents=True)

    (tool_dir / "tool.yaml").write_text(
        yaml.dump({
            "name": "function_tool",
            "version": "1.0",
            "type": "function",
            "description": "A sample function tool.",
            "config": {"async_mode": True},
            "execution": {"retries": 0, "timeout": 5},
        })
    )
    (tool_dir / "request.proto").write_text(
        'syntax = "proto3";\nmessage FunctionRequest { string text = 1; }\n'
    )
    (tool_dir / "response.proto").write_text(
        'syntax = "proto3";\nmessage FunctionResponse { string output = 1; }\n'
    )
    (tool_dir / "logic.py").write_text(
        "async def run(inputs):\n    return {'output': inputs.get('text', '') + '_ok'}\n"
    )
    return tool_dir


@pytest.fixture()
def mock_tool_definition() -> Any:
    """Return a minimal MagicMock ToolDefinition for unit testing."""
    from agent_tools.core.definition import ExecutionConfig, ToolDefinition
    from agent_tools.handlers.api_handler import APIHandler

    defn = ToolDefinition(
        name="mock_tool",
        version="1.0",
        type="api",
        description="Mock tool",
        config={
            "endpoint": "https://api.example.com/v1/mock",
            "method": "GET",
            "auth": {},
            "params": {},
        },
        execution=ExecutionConfig(retries=0, timeout=5),
        handler_class=APIHandler,
        proto_input=None,
        proto_output=None,
    )
    return defn


@pytest.fixture(autouse=True)
def reset_settings():
    """Clear the Settings lru_cache before each test."""
    from agent_tools.core.settings import Settings
    Settings._reset()
    yield
    Settings._reset()
