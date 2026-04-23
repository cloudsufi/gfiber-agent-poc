"""Shared pytest fixtures for the agent_tools test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture()
def tmp_tools_dir(tmp_path: Path) -> Path:
    """Return an empty temporary directory suitable for use as tools_dir."""
    return tmp_path / "tools"


@pytest.fixture()
def sample_api_tool_dir(tmp_path: Path) -> Path:
    """Create a minimal valid ``type: api`` tool directory with YAML schemas."""
    tool_dir = tmp_path / "tools" / "sample_tool"
    tool_dir.mkdir(parents=True)

    (tool_dir / "tool.yaml").write_text(
        yaml.dump(
            {
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
            }
        )
    )
    (tool_dir / "input.yaml").write_text(
        yaml.dump(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            }
        )
    )
    (tool_dir / "output.yaml").write_text(
        yaml.dump(
            {
                "type": "object",
                "properties": {"result": {"type": "string"}},
            }
        )
    )
    return tool_dir


@pytest.fixture()
def sample_function_tool_dir(tmp_path: Path) -> Path:
    """Create a minimal valid ``type: function`` tool directory."""
    tool_dir = tmp_path / "tools" / "function_tool"
    tool_dir.mkdir(parents=True)

    (tool_dir / "tool.yaml").write_text(
        yaml.dump(
            {
                "name": "function_tool",
                "version": "1.0",
                "type": "function",
                "description": "A sample function tool.",
                "config": {"async_mode": True},
                "execution": {"retries": 0, "timeout": 5},
            }
        )
    )
    (tool_dir / "input.yaml").write_text(
        yaml.dump(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["text"],
                "properties": {"text": {"type": "string"}},
            }
        )
    )
    (tool_dir / "output.yaml").write_text(
        yaml.dump(
            {
                "type": "object",
                "properties": {"output": {"type": "string"}},
            }
        )
    )
    (tool_dir / "logic.py").write_text(
        "async def run(tool_context, inputs):\n    return {'output': inputs.get('text', '') + '_ok'}\n"
    )
    return tool_dir


@pytest.fixture()
def mock_tool_definition() -> Any:
    """Return a minimal ToolDefinition for unit testing."""
    from agent_tools.core.definition import ExecutionConfig, ToolDefinition
    from agent_tools.handlers.api_handler import APIHandler

    return ToolDefinition(
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
        input_schema=None,
        output_schema=None,
    )


@pytest.fixture(autouse=True)
def reset_settings():
    """Clear the Settings lru_cache before each test."""
    from agent_tools.core.settings import Settings

    Settings._reset()
    yield
    Settings._reset()
