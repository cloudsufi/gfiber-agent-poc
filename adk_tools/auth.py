"""
Build ADK-native auth objects from validated AuthConfig models.

Two public functions are provided — one per ADK tool type that supports auth:

* :func:`build_openapi_auth` — returns ``(auth_scheme, auth_credential)``
  for ``google.adk.tools.openapi_tool.OpenAPIToolset``.

* :func:`build_mcp_headers` — returns a plain ``dict[str, str]`` of HTTP
  headers passed to ``google.adk.tools.mcp_tool.MCPToolset`` via
  ``SseServerParams(headers=...)``.

Auth types supported
--------------------
====================  ========================================================
 Config model          Resolution
====================  ========================================================
 BearerAuthConfig      Reads token from ``os.environ[token_env]``.
                       Injected as ``Authorization: Bearer <token>``.
 APIKeyAuthConfig      Reads key from ``os.environ[key_env]``.
                       Sent in the configured header / query / cookie.
 OAuth2AuthConfig      Fetches a client-credentials access token via httpx
                       and injects it as a bearer.  (OpenAPI only)
 ServiceAccountAuthConfig  Resolves SA JSON from env var or file path and
                       mints an access/ID token via google-auth.
====================  ========================================================

All credential lookups happen at tool-build time (startup) so missing env
vars fail fast before the agent handles any request.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from .models import (
    APIKeyAuthConfig,
    AuthConfig,
    BearerAuthConfig,
    OAuth2AuthConfig,
    ServiceAccountAuthConfig,
)

log = logging.getLogger("adk_tools.auth")


# ── Credential resolution ──────────────────────────────────────────────────────


def _resolve_credential(
    *,
    env: Optional[str],
    secret: Optional[str],
    label: str,
) -> str:
    """
    Resolve a credential value from either an env var or GCP Secret Manager.

    Exactly one of *env* / *secret* should be set (enforced by Pydantic).
    Raises early with a clear message if the value is absent.
    """
    if env:
        return _require_env(env, label)
    if secret:
        return _read_gcp_secret(secret, label)
    raise ValueError(f"Auth: no source configured for '{label}'")


def _read_gcp_secret(resource_name: str, label: str) -> str:
    """
    Read a secret payload from Google Cloud Secret Manager.

    :param resource_name: Full resource name, e.g.
        ``projects/my-project/secrets/my-secret/versions/latest``
    :raises ImportError: if google-cloud-secret-manager is not installed.
    :raises ValueError: if the secret is empty.
    """
    try:
        from google.cloud import secretmanager  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "google-cloud-secret-manager is required to read credentials from "
            "GCP Secret Manager.  Install: pip install google-cloud-secret-manager"
        ) from exc

    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(name=resource_name)
    value = response.payload.data.decode("utf-8").strip()
    if not value:
        raise ValueError(
            f"Auth: GCP Secret '{resource_name}' is empty ({label}). "
            "Ensure the secret version contains a non-empty value."
        )
    log.debug("auth: resolved %s from GCP Secret Manager (%s)", label, resource_name)
    return value


# ── OpenAPI auth ───────────────────────────────────────────────────────────────


def build_openapi_auth(auth: Optional[AuthConfig]) -> tuple[Any, Any]:
    """
    Translate an :class:`AuthConfig` into an ADK ``(auth_scheme, auth_credential)``
    tuple for use with ``OpenAPIToolset(auth_scheme=..., auth_credential=...)``.

    Returns ``(None, None)`` when *auth* is ``None``.

    :raises ImportError: if ``google-adk`` is not installed.
    :raises EnvironmentError: if a required env var is not set.
    """
    if auth is None:
        return None, None

    try:
        from google.adk.tools.openapi_tool.auth.auth_helpers import (  # type: ignore[import]
            service_account_dict_to_scheme_credential,
            token_to_scheme_credential,
        )
    except ImportError as exc:
        raise ImportError(
            "google-adk is required for OpenAPI tools. "
            "Install: pip install google-adk"
        ) from exc

    if isinstance(auth, BearerAuthConfig):
        token = _resolve_credential(env=auth.token_env, secret=auth.token_secret, label="bearer token")
        return token_to_scheme_credential("oauth2Token", "header", "Authorization", token)

    if isinstance(auth, APIKeyAuthConfig):
        key = _resolve_credential(env=auth.key_env, secret=auth.key_secret, label="API key")
        return token_to_scheme_credential("apikey", auth.location, auth.header_name, key)

    if isinstance(auth, ServiceAccountAuthConfig):
        sa_dict = _resolve_service_account_json(env=auth.key_env, secret=auth.key_secret)
        return service_account_dict_to_scheme_credential(sa_dict, auth.scopes)

    if isinstance(auth, OAuth2AuthConfig):
        # OAuth2 client-credentials: mint a token and treat as bearer.
        token = _fetch_oauth2_token(auth)
        return token_to_scheme_credential("oauth2Token", "header", "Authorization", token)

    log.warning("build_openapi_auth: unhandled auth type %s — proceeding without auth", type(auth))
    return None, None


# ── MCP auth ───────────────────────────────────────────────────────────────────


def build_mcp_headers(auth: Optional[AuthConfig]) -> dict[str, str]:
    """
    Translate an :class:`AuthConfig` into HTTP headers for MCP SSE transport.

    Passed to ``SseServerParams(headers=...)`` when constructing an
    ``MCPToolset``. Returns ``{}`` when *auth* is ``None``.

    Note: query / cookie auth types cannot be expressed as HTTP headers and
    are silently ignored here — configure them directly on the server if needed.
    """
    if auth is None:
        return {}

    if isinstance(auth, BearerAuthConfig):
        token = _resolve_credential(env=auth.token_env, secret=auth.token_secret, label="bearer token")
        return {"Authorization": f"Bearer {token}"}

    if isinstance(auth, APIKeyAuthConfig):
        key = _resolve_credential(env=auth.key_env, secret=auth.key_secret, label="API key")
        if auth.location == "header":
            return {auth.header_name: key}
        log.warning(
            "build_mcp_headers: API key with location=%s cannot be set as a header — skipping",
            auth.location,
        )
        return {}

    if isinstance(auth, OAuth2AuthConfig):
        token = _fetch_oauth2_token(auth)
        return {"Authorization": f"Bearer {token}"}

    if isinstance(auth, ServiceAccountAuthConfig):
        token = _mint_service_account_token(auth)
        return {"Authorization": f"Bearer {token}"} if token else {}

    log.warning("build_mcp_headers: unhandled auth type %s — no headers added", type(auth))
    return {}


# ── Internal helpers ───────────────────────────────────────────────────────────


def _require_env(var_name: str, label: str) -> str:
    """Read *var_name* from env; raise :class:`EnvironmentError` if missing or empty."""
    value = os.environ.get(var_name, "").strip()
    if not value:
        raise EnvironmentError(
            f"Auth: {label} env var '{var_name}' is not set or empty. "
            f"Export it before starting the agent."
        )
    return value


def _resolve_service_account_json(
    *, env: Optional[str], secret: Optional[str]
) -> dict[str, Any]:
    """
    Resolve the SA JSON from an env var or GCP Secret Manager.

    The resolved value may be:
    - A raw JSON string (``{"type": "service_account", ...}``), or
    - A filesystem path to a ``.json`` key file (env only).
    """
    raw = _resolve_credential(env=env, secret=secret, label="service account key")
    if raw.lstrip().startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Auth: service account value looks like JSON but failed to parse: {exc}"
            ) from exc
    if env and os.path.isfile(raw):
        with open(raw) as fh:
            return json.load(fh)
    raise ValueError(
        "Auth: service account value is neither valid JSON nor an existing file path."
    )


def _fetch_oauth2_token(auth: OAuth2AuthConfig) -> str:
    """Fetch a client-credentials access token (synchronous httpx call)."""
    try:
        import httpx  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "httpx is required for OAuth2 auth. Install: pip install httpx"
        ) from exc

    client_id = _resolve_credential(
        env=auth.client_id_env, secret=auth.client_id_secret, label="OAuth2 client_id"
    )
    client_secret = _resolve_credential(
        env=auth.client_secret_env, secret=auth.client_secret_secret, label="OAuth2 client_secret"
    )
    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if auth.scope:
        data["scope"] = auth.scope

    resp = httpx.post(auth.token_url, data=data, timeout=30)
    resp.raise_for_status()
    token = resp.json().get("access_token", "")
    if not token:
        raise ValueError(f"OAuth2 token response missing 'access_token': {resp.text[:200]}")
    return token


def _mint_service_account_token(auth: ServiceAccountAuthConfig) -> str:
    """Mint a GCP access or ID token from a service-account key."""
    try:
        from google.auth.transport.requests import Request  # type: ignore[import]
        from google.oauth2 import service_account  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "google-auth is required for service_account auth. "
            "Install: pip install google-auth"
        ) from exc

    sa_dict = _resolve_service_account_json(env=auth.key_env, secret=auth.key_secret)

    if auth.audience:
        creds = service_account.IDTokenCredentials.from_service_account_info(
            sa_dict, target_audience=auth.audience
        )
    else:
        creds = service_account.Credentials.from_service_account_info(
            sa_dict,
            scopes=auth.scopes or ["https://www.googleapis.com/auth/cloud-platform"],
        )

    creds.refresh(Request())
    return creds.token or ""
