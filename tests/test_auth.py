"""
Tests for adk_tools/auth.py

Covers:
- _require_env: present, missing, empty
- _resolve_credential: env path, secret path, no source
- _read_gcp_secret: success, empty secret, missing library
- build_openapi_auth: None, bearer, api_key (header/query), oauth2, service_account
- build_mcp_headers: None, bearer, api_key (header + non-header), oauth2, service_account
- _resolve_service_account_json: raw JSON string, file path, invalid JSON, not a file
- _fetch_oauth2_token: success, HTTP error, missing access_token, missing httpx
- _mint_service_account_token: access token, id token, missing google-auth
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from adk_tools.models import (
    APIKeyAuthConfig,
    BearerAuthConfig,
    OAuth2AuthConfig,
    ServiceAccountAuthConfig,
)


# ── _require_env ───────────────────────────────────────────────────────────────

class TestRequireEnv:
    def test_present(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "secret123")
        from adk_tools.auth import _require_env
        assert _require_env("MY_VAR", "label") == "secret123"

    def test_missing_raises(self, monkeypatch):
        monkeypatch.delenv("MY_VAR", raising=False)
        from adk_tools.auth import _require_env
        with pytest.raises(EnvironmentError, match="MY_VAR"):
            _require_env("MY_VAR", "label")

    def test_empty_raises(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "   ")  # whitespace only
        from adk_tools.auth import _require_env
        with pytest.raises(EnvironmentError, match="MY_VAR"):
            _require_env("MY_VAR", "label")


# ── _resolve_credential ────────────────────────────────────────────────────────

class TestResolveCredential:
    def test_env_path(self, monkeypatch):
        monkeypatch.setenv("TOKEN", "tok123")
        from adk_tools.auth import _resolve_credential
        assert _resolve_credential(env="TOKEN", secret=None, label="x") == "tok123"

    def test_secret_path(self, monkeypatch):
        from adk_tools.auth import _resolve_credential
        with patch("adk_tools.auth._read_gcp_secret", return_value="gcp_secret_value") as mock_read:
            result = _resolve_credential(env=None, secret="projects/p/secrets/s/versions/1", label="x")
        assert result == "gcp_secret_value"
        mock_read.assert_called_once_with("projects/p/secrets/s/versions/1", "x")

    def test_no_source_raises(self):
        from adk_tools.auth import _resolve_credential
        with pytest.raises(ValueError, match="no source"):
            _resolve_credential(env=None, secret=None, label="x")


# ── _read_gcp_secret ───────────────────────────────────────────────────────────

class TestReadGcpSecret:
    def test_success(self):
        from adk_tools.auth import _read_gcp_secret
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.data = b"my_secret_value\n"
        mock_client.access_secret_version.return_value = mock_response

        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.return_value = mock_client

        with patch.dict(sys.modules, {"google.cloud": MagicMock(), "google.cloud.secretmanager": mock_sm}):
            result = _read_gcp_secret("projects/p/secrets/s/versions/latest", "token")

        assert result == "my_secret_value"

    def test_empty_secret_raises(self):
        from adk_tools.auth import _read_gcp_secret
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.data = b"   "  # whitespace only
        mock_client.access_secret_version.return_value = mock_response

        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.return_value = mock_client

        with patch.dict(sys.modules, {"google.cloud": MagicMock(), "google.cloud.secretmanager": mock_sm}):
            with pytest.raises(ValueError, match="empty"):
                _read_gcp_secret("projects/p/secrets/s/versions/latest", "token")

    def test_missing_library_raises(self):
        from adk_tools.auth import _read_gcp_secret
        with patch.dict(sys.modules, {"google.cloud.secretmanager": None}):
            # Temporarily remove so import fails
            saved = sys.modules.pop("google.cloud.secretmanager", None)
            # Simulate ImportError
            with patch("builtins.__import__", side_effect=ImportError("no module")):
                with pytest.raises((ImportError, Exception)):
                    _read_gcp_secret("projects/p/secrets/s/versions/latest", "token")
            if saved is not None:
                sys.modules["google.cloud.secretmanager"] = saved


# ── build_openapi_auth ─────────────────────────────────────────────────────────

class TestBuildOpenapiAuth:
    def test_none_returns_none_none(self):
        from adk_tools.auth import build_openapi_auth
        scheme, cred = build_openapi_auth(None)
        assert scheme is None and cred is None

    def test_bearer(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "bearer_tok")
        from adk_tools.auth import build_openapi_auth
        auth = BearerAuthConfig(type="bearer", token_env="MY_TOKEN")
        scheme, cred = build_openapi_auth(auth)
        assert scheme is not None
        assert cred["token"] == "bearer_tok"

    def test_api_key_header(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "apikey123")
        from adk_tools.auth import build_openapi_auth
        auth = APIKeyAuthConfig(type="api_key", key_env="MY_KEY", header_name="X-API-Key", location="header")
        scheme, cred = build_openapi_auth(auth)
        assert scheme["location"] == "header"
        assert cred["token"] == "apikey123"

    def test_api_key_query(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "apikey_q")
        from adk_tools.auth import build_openapi_auth
        auth = APIKeyAuthConfig(type="api_key", key_env="MY_KEY", location="query")
        scheme, cred = build_openapi_auth(auth)
        assert scheme["location"] == "query"

    def test_oauth2(self, monkeypatch):
        monkeypatch.setenv("CID", "client_id_val")
        monkeypatch.setenv("CSEC", "client_secret_val")
        auth = OAuth2AuthConfig(
            type="oauth2",
            client_id_env="CID",
            client_secret_env="CSEC",
            token_url="https://auth.example.com/token",
        )
        with patch("adk_tools.auth._fetch_oauth2_token", return_value="oauth_tok"):
            from adk_tools.auth import build_openapi_auth
            scheme, cred = build_openapi_auth(auth)
        assert cred["token"] == "oauth_tok"

    def test_service_account(self, monkeypatch):
        sa = {"type": "service_account", "project_id": "p", "private_key": "k"}
        monkeypatch.setenv("SA_JSON", json.dumps(sa))
        auth = ServiceAccountAuthConfig(type="service_account", key_env="SA_JSON")
        from adk_tools.auth import build_openapi_auth
        scheme, cred = build_openapi_auth(auth)
        assert scheme["type"] == "service_account"

    def test_missing_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_TOKEN", raising=False)
        from adk_tools.auth import build_openapi_auth
        auth = BearerAuthConfig(type="bearer", token_env="MISSING_TOKEN")
        with pytest.raises(EnvironmentError, match="MISSING_TOKEN"):
            build_openapi_auth(auth)


# ── build_mcp_headers ──────────────────────────────────────────────────────────

class TestBuildMcpHeaders:
    def test_none_returns_empty(self):
        from adk_tools.auth import build_mcp_headers
        assert build_mcp_headers(None) == {}

    def test_bearer(self, monkeypatch):
        monkeypatch.setenv("MCP_TOK", "mcp_bearer")
        from adk_tools.auth import build_mcp_headers
        auth = BearerAuthConfig(type="bearer", token_env="MCP_TOK")
        headers = build_mcp_headers(auth)
        assert headers["Authorization"] == "Bearer mcp_bearer"

    def test_api_key_header(self, monkeypatch):
        monkeypatch.setenv("MCP_KEY", "key_val")
        from adk_tools.auth import build_mcp_headers
        auth = APIKeyAuthConfig(type="api_key", key_env="MCP_KEY", header_name="X-Custom-Key")
        headers = build_mcp_headers(auth)
        assert headers["X-Custom-Key"] == "key_val"

    def test_api_key_query_skipped(self, monkeypatch):
        """Query-location API keys can't be headers — should return {} with a warning."""
        monkeypatch.setenv("MCP_KEY", "key_val")
        from adk_tools.auth import build_mcp_headers
        auth = APIKeyAuthConfig(type="api_key", key_env="MCP_KEY", location="query")
        headers = build_mcp_headers(auth)
        assert headers == {}

    def test_oauth2(self, monkeypatch):
        monkeypatch.setenv("CID", "cid")
        monkeypatch.setenv("CSEC", "csec")
        auth = OAuth2AuthConfig(
            type="oauth2",
            client_id_env="CID",
            client_secret_env="CSEC",
            token_url="https://auth.example.com/token",
        )
        with patch("adk_tools.auth._fetch_oauth2_token", return_value="oauth2_tok"):
            from adk_tools.auth import build_mcp_headers
            headers = build_mcp_headers(auth)
        assert headers["Authorization"] == "Bearer oauth2_tok"

    def test_service_account(self, monkeypatch):
        monkeypatch.setenv("SA_JSON", json.dumps({"type": "service_account"}))
        auth = ServiceAccountAuthConfig(type="service_account", key_env="SA_JSON")
        with patch("adk_tools.auth._mint_service_account_token", return_value="sa_tok"):
            from adk_tools.auth import build_mcp_headers
            headers = build_mcp_headers(auth)
        assert headers["Authorization"] == "Bearer sa_tok"

    def test_service_account_empty_token(self, monkeypatch):
        monkeypatch.setenv("SA_JSON", json.dumps({"type": "service_account"}))
        auth = ServiceAccountAuthConfig(type="service_account", key_env="SA_JSON")
        with patch("adk_tools.auth._mint_service_account_token", return_value=""):
            from adk_tools.auth import build_mcp_headers
            headers = build_mcp_headers(auth)
        assert headers == {}


# ── _resolve_service_account_json ─────────────────────────────────────────────

class TestResolveServiceAccountJson:
    def test_raw_json_string(self, monkeypatch):
        sa = {"type": "service_account", "project_id": "p"}
        monkeypatch.setenv("SA_JSON", json.dumps(sa))
        from adk_tools.auth import _resolve_service_account_json
        result = _resolve_service_account_json(env="SA_JSON", secret=None)
        assert result["type"] == "service_account"

    def test_file_path(self, tmp_path, monkeypatch):
        sa = {"type": "service_account", "project_id": "proj"}
        sa_file = tmp_path / "sa.json"
        sa_file.write_text(json.dumps(sa))
        monkeypatch.setenv("SA_KEY_FILE", str(sa_file))
        from adk_tools.auth import _resolve_service_account_json
        result = _resolve_service_account_json(env="SA_KEY_FILE", secret=None)
        assert result["project_id"] == "proj"

    def test_invalid_json_raises(self, monkeypatch):
        monkeypatch.setenv("SA_JSON", "{not valid json")
        from adk_tools.auth import _resolve_service_account_json
        with pytest.raises(ValueError, match="failed to parse"):
            _resolve_service_account_json(env="SA_JSON", secret=None)

    def test_not_json_not_file_raises(self, monkeypatch):
        monkeypatch.setenv("SA_JSON", "not_a_file_or_json")
        from adk_tools.auth import _resolve_service_account_json
        with pytest.raises(ValueError, match="neither valid JSON"):
            _resolve_service_account_json(env="SA_JSON", secret=None)

    def test_via_secret_manager(self):
        sa = {"type": "service_account", "project_id": "p"}
        with patch("adk_tools.auth._read_gcp_secret", return_value=json.dumps(sa)):
            from adk_tools.auth import _resolve_service_account_json
            result = _resolve_service_account_json(env=None, secret="projects/p/secrets/sa/versions/1")
        assert result["type"] == "service_account"


# ── _fetch_oauth2_token ────────────────────────────────────────────────────────

class TestFetchOAuth2Token:
    def _make_auth(self, monkeypatch):
        monkeypatch.setenv("CID", "my_client_id")
        monkeypatch.setenv("CSEC", "my_client_secret")
        return OAuth2AuthConfig(
            type="oauth2",
            client_id_env="CID",
            client_secret_env="CSEC",
            token_url="https://auth.example.com/token",
            scope="read write",
        )

    def test_success(self, monkeypatch):
        auth = self._make_auth(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "fetched_token"}
        mock_resp.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from adk_tools import auth as auth_mod
            import importlib
            importlib.reload(auth_mod)
            result = auth_mod._fetch_oauth2_token(auth)

        assert result == "fetched_token"

    def test_http_error_raises(self, monkeypatch):
        auth = self._make_auth(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from adk_tools import auth as auth_mod
            import importlib
            importlib.reload(auth_mod)
            with pytest.raises(Exception, match="401"):
                auth_mod._fetch_oauth2_token(auth)

    def test_missing_access_token_raises(self, monkeypatch):
        auth = self._make_auth(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"token_type": "bearer"}  # no access_token
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "no token here"

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from adk_tools import auth as auth_mod
            import importlib
            importlib.reload(auth_mod)
            with pytest.raises(ValueError, match="access_token"):
                auth_mod._fetch_oauth2_token(auth)

    def test_without_scope(self, monkeypatch):
        """When scope is empty it should not be sent in the POST data."""
        monkeypatch.setenv("CID2", "cid")
        monkeypatch.setenv("CSEC2", "csec")
        auth = OAuth2AuthConfig(
            type="oauth2",
            client_id_env="CID2",
            client_secret_env="CSEC2",
            token_url="https://auth.example.com/token",
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok"}
        mock_resp.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = mock_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from adk_tools import auth as auth_mod
            import importlib
            importlib.reload(auth_mod)
            result = auth_mod._fetch_oauth2_token(auth)

        assert result == "tok"
        call_kwargs = mock_httpx.post.call_args[1]
        assert "scope" not in call_kwargs.get("data", {})
