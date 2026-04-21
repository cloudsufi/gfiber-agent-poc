"""Unit tests for agent_tools.core.settings."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_tools.core.settings import Settings, _PACKAGE_ROOT


class TestSettings:
    def test_defaults(self):
        s = Settings.load()
        assert s.tools_dir == _PACKAGE_ROOT / "tools"
        assert s.default_timeout == 30
        assert s.default_retries == 3
        assert s.log_level == "INFO"

    def test_env_override_tools_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_TOOLS_DIR", str(tmp_path))
        s = Settings.load()
        assert s.tools_dir == tmp_path

    def test_env_override_timeout(self, monkeypatch):
        monkeypatch.setenv("AGENT_TOOLS_TIMEOUT", "60")
        s = Settings.load()
        assert s.default_timeout == 60

    def test_env_override_retries(self, monkeypatch):
        monkeypatch.setenv("AGENT_TOOLS_RETRIES", "5")
        s = Settings.load()
        assert s.default_retries == 5

    def test_env_override_log_level(self, monkeypatch):
        monkeypatch.setenv("AGENT_TOOLS_LOG_LEVEL", "DEBUG")
        s = Settings.load()
        assert s.log_level == "DEBUG"

    def test_is_frozen(self):
        s = Settings.load()
        with pytest.raises((TypeError, AttributeError)):
            s.log_level = "DEBUG"  # type: ignore[misc]

    def test_reset_clears_cache(self, monkeypatch):
        s1 = Settings.load()
        monkeypatch.setenv("AGENT_TOOLS_TIMEOUT", "99")
        s2 = Settings.load()
        assert s1.default_timeout == s2.default_timeout  # same cached instance

        Settings._reset()
        s3 = Settings.load()
        assert s3.default_timeout == 99
