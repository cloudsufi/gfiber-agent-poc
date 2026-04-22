"""Tests for the new SecretRef-based auth resolver paths."""
from __future__ import annotations

import base64

from agent_tools.core.context import with_request_headers
from agent_tools.middleware.auth import resolve_auth


class TestSecretRefSources:
    def test_env_source_explicit(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "env-value")
        result = resolve_auth(
            {"bearer": {"token": {"source": "ENV", "name": "MY_TOKEN"}}}
        )
        assert result == {"type": "bearer", "token": "env-value"}

    def test_header_source(self):
        with with_request_headers({"X-Caller-Token": "from-header"}):
            result = resolve_auth(
                {"bearer": {"token": {"source": "HEADER", "name": "X-Caller-Token"}}}
            )
        assert result == {"type": "bearer", "token": "from-header"}

    def test_header_source_is_case_insensitive(self):
        with with_request_headers({"x-caller-token": "lowercased"}):
            result = resolve_auth(
                {"bearer": {"token": {"source": "HEADER", "name": "X-CALLER-TOKEN"}}}
            )
        assert result == {"type": "bearer", "token": "lowercased"}

    def test_parameter_source(self):
        result = resolve_auth(
            {"bearer": {"token": {"source": "PARAMETER", "name": "caller_token"}}},
            request_input={"caller_token": "from-param"},
        )
        assert result == {"type": "bearer", "token": "from-param"}

    def test_gcp_secret_source_missing_client_returns_empty(self, monkeypatch):
        """When google-cloud-secret-manager isn't installed the resolver degrades gracefully."""
        import builtins

        real_import = builtins.__import__

        def block_secret_manager(name, *a, **kw):
            if name == "google.cloud.secretmanager" or name == "google.cloud":
                raise ImportError("forced")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", block_secret_manager)
        result = resolve_auth(
            {
                "bearer": {
                    "token": {
                        "source": "GCP_SECRET",
                        "name": "projects/p/secrets/s/versions/latest",
                    }
                }
            }
        )
        assert result["token"] == ""


class TestLegacyAndNewCoexist:
    def test_legacy_api_key_still_works(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "legacy-value")
        result = resolve_auth(
            {"api_key": {"header_name": "X-Api-Key", "key_env": "MY_KEY"}}
        )
        assert result == {"type": "api_key", "header": "X-Api-Key", "value": "legacy-value"}

    def test_new_api_key_with_secret_ref(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "new-value")
        result = resolve_auth(
            {
                "api_key": {
                    "header_name": "X-Api-Key",
                    "key": {"source": "ENV", "name": "MY_KEY"},
                }
            }
        )
        assert result == {"type": "api_key", "header": "X-Api-Key", "value": "new-value"}

    def test_basic_legacy_fields(self, monkeypatch):
        monkeypatch.setenv("U", "alice")
        monkeypatch.setenv("P", "hunter2")
        result = resolve_auth(
            {"basic": {"username_env": "U", "password_env": "P"}}
        )
        expected = base64.b64encode(b"alice:hunter2").decode()
        assert result == {"type": "basic", "encoded": expected}

    def test_basic_secret_ref(self, monkeypatch):
        monkeypatch.setenv("U", "alice")
        monkeypatch.setenv("P", "hunter2")
        result = resolve_auth(
            {
                "basic": {
                    "username": {"source": "ENV", "name": "U"},
                    "password": {"source": "ENV", "name": "P"},
                }
            }
        )
        expected = base64.b64encode(b"alice:hunter2").decode()
        assert result == {"type": "basic", "encoded": expected}


class TestServiceAgentGracefulDegradation:
    def test_no_adc_returns_empty(self, monkeypatch):
        """Without application default credentials the resolver returns {}, not raises."""
        import google.auth

        def boom(*a, **kw):
            raise google.auth.exceptions.DefaultCredentialsError("no ADC")

        monkeypatch.setattr("google.auth.default", boom)
        result = resolve_auth({"service_agent": {"scopes": []}})
        assert result == {}
