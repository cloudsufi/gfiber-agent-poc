"""
AuthMiddleware — resolves typed AuthConfig credentials at call time.

Reads the ``auth`` sub-dict from the tool's validated config and injects
``ctx.resolved_auth`` so handlers never touch env vars directly.
"""
from __future__ import annotations

import base64
import os
from typing import Any


class AuthMiddleware:
    """Resolve AuthConfig credentials and inject into ExecutionContext."""

    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        async def _auth(ctx):  # type: ignore[no-untyped-def]
            auth_cfg = ctx.tool_def.config.get("auth", {})
            ctx.resolved_auth = resolve_auth(auth_cfg)
            return await next_fn(ctx)

        return _auth


def resolve_auth(auth: dict[str, Any]) -> dict[str, Any]:
    """
    Convert an ``AuthConfig`` dict (produced by proto round-trip) into a
    ready-to-use credential dict keyed by ``type``.

    Returns an empty dict if no auth is configured.
    """
    if not auth:
        return {}

    if "bearer" in auth and auth["bearer"]:
        env_name = auth["bearer"].get("token_env", "")
        token = os.environ.get(env_name, "")
        return {"type": "bearer", "token": token}

    if "api_key" in auth and auth["api_key"]:
        cfg = auth["api_key"]
        value = os.environ.get(cfg.get("key_env", ""), "")
        return {"type": "api_key", "header": cfg.get("header_name", ""), "value": value}

    if "oauth2" in auth and auth["oauth2"]:
        return _fetch_oauth2_token(auth["oauth2"])

    if "basic" in auth and auth["basic"]:
        cfg = auth["basic"]
        username = os.environ.get(cfg.get("username_env", ""), "")
        password = os.environ.get(cfg.get("password_env", ""), "")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"type": "basic", "encoded": encoded}

    return {}


def _fetch_oauth2_token(cfg: dict[str, Any]) -> dict[str, Any]:
    """Fetch an OAuth2 client-credentials access token synchronously."""
    import httpx

    client_id = os.environ.get(cfg.get("client_id_env", ""), "")
    client_secret = os.environ.get(cfg.get("client_secret_env", ""), "")
    token_url = cfg.get("token_url", "")
    scope = cfg.get("scope", "")

    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        data["scope"] = scope

    resp = httpx.post(token_url, data=data, timeout=30)
    resp.raise_for_status()
    token = resp.json().get("access_token", "")
    return {"type": "bearer", "token": token}
