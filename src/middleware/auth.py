"""
AuthMiddleware — resolves typed AuthConfig credentials at call time.

Position in the pipeline
------------------------
AuthMiddleware is the **outermost** wrapper in the default pipeline —
credentials are resolved exactly once per call, before retries or schema
validation run. That matters for OAuth2 and service-account auth, where
"resolve" means "mint a token", and doing it per retry attempt would cost
real latency and quota.

Inputs and outputs
------------------
* **Input**:  ``ctx.tool_def.config["auth"]`` — a dict produced by schema
  round-trip of the tool's ``AuthConfig`` block. Always a oneof-style
  mapping like ``{"bearer": {"token": {...}}}``.
* **Output**: ``ctx.resolved_auth`` — a flat dict that handlers consume.
  Shapes per type::

    {"type": "bearer",  "token":  "<resolved-token>"}
    {"type": "api_key", "header": "<name>", "value": "<resolved-key>"}
    {"type": "basic",   "encoded": "<base64 user:pass>"}
    {}     # no auth configured, or unknown / unresolvable

Credential sources (SecretRef)
------------------------------
Each credential field is a ``SecretRef`` that names WHERE the value lives:

=============  ==========================================================
 ``source``     Resolution
=============  ==========================================================
 ``ENV``        ``os.environ[<name>]``. Default for anyone not specifying.
 ``HEADER``     Inbound header supplied by the agent via
                ``with_request_headers(...)`` / ``_headers=`` kwarg.
                Case-insensitive lookup.
 ``PARAMETER``  Value from ``ctx.validated_input[<name>]`` — i.e. a field
                on the validated request.
 ``GCP_SECRET`` Google Secret Manager resource name
                ``projects/P/secrets/S/versions/V``. Resolved on-demand
                via ``google-cloud-secret-manager``.
=============  ==========================================================

Legacy ``*_env`` string fields (``token_env``, ``key_env``, …) are still
accepted. They up-convert to ``{source: ENV, name: <value>}`` at resolve
time so older ``tool.yaml`` files keep working without edits.

Google-specific auth types
--------------------------
* ``service_account`` — reads a GCP service-account JSON (from env, file
  path, or Secret Manager) and uses ``google.oauth2.service_account`` to
  mint an access token (or ID token when ``audience`` is set).
* ``service_agent`` — uses Application Default Credentials, optionally
  impersonating a ``target_principal`` via
  ``google.auth.impersonated_credentials``. Degrades to ``{}`` cleanly when
  ADC isn't configured, so demos that enable a CTA tool in mock mode
  don't fail on laptops without ``gcloud auth`` set up.

Handlers never touch env vars, files, or Secret Manager directly — they
always read the resolved value from ``ctx.resolved_auth``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import Mapping
from typing import Any

from agent_tools.core.context import current_request_headers

log = logging.getLogger("agent_tools.auth")


class AuthMiddleware:
    """Resolve AuthConfig credentials and inject into ExecutionContext."""

    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        async def _auth(ctx):  # type: ignore[no-untyped-def]
            auth_cfg = ctx.tool_def.config.get("auth", {})
            ctx.resolved_auth = resolve_auth(auth_cfg, ctx.validated_input)
            return await next_fn(ctx)

        return _auth


# ── public ────────────────────────────────────────────────────────────────────


def resolve_auth(
    auth: Mapping[str, Any],
    request_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve an ``AuthConfig`` dict into a ready-to-use credential dict.

    Returns ``{}`` when no auth is configured.
    """
    if not auth:
        return {}
    request_input = request_input or {}

    if auth.get("bearer"):
        cfg = auth["bearer"]
        ref = _ref_or_legacy(cfg, "token", "token_env")
        return {"type": "bearer", "token": _resolve_secret_ref(ref, request_input)}

    if auth.get("api_key"):
        cfg = auth["api_key"]
        ref = _ref_or_legacy(cfg, "key", "key_env")
        return {
            "type": "api_key",
            "header": cfg.get("header_name", ""),
            "value": _resolve_secret_ref(ref, request_input),
        }

    if auth.get("oauth2"):
        cfg = auth["oauth2"]
        client_id = _resolve_secret_ref(
            _ref_or_legacy(cfg, "client_id", "client_id_env"), request_input
        )
        client_secret = _resolve_secret_ref(
            _ref_or_legacy(cfg, "client_secret", "client_secret_env"), request_input
        )
        return _fetch_oauth2_token(
            client_id=client_id,
            client_secret=client_secret,
            token_url=cfg.get("token_url", ""),
            scope=cfg.get("scope", ""),
        )

    if auth.get("basic"):
        cfg = auth["basic"]
        username = _resolve_secret_ref(
            _ref_or_legacy(cfg, "username", "username_env"), request_input
        )
        password = _resolve_secret_ref(
            _ref_or_legacy(cfg, "password", "password_env"), request_input
        )
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"type": "basic", "encoded": encoded}

    if auth.get("service_account"):
        cfg = auth["service_account"]
        return _fetch_service_account_token(
            credentials_ref=cfg.get("credentials", {}),
            scopes=list(cfg.get("scopes", [])),
            audience=cfg.get("audience", ""),
            request_input=request_input,
        )

    if auth.get("service_agent"):
        cfg = auth["service_agent"]
        return _fetch_service_agent_token(
            target_principal=cfg.get("target_principal", ""),
            scopes=list(cfg.get("scopes", [])),
            audience=cfg.get("audience", ""),
        )

    return {}


# ── internal ──────────────────────────────────────────────────────────────────


def _ref_or_legacy(
    cfg: Mapping[str, Any],
    ref_field: str,
    legacy_env_field: str,
) -> dict[str, Any]:
    """Return a SecretRef dict, up-converting legacy ``*_env`` fields."""
    ref = cfg.get(ref_field)
    if ref and (ref.get("name") or ref.get("source")):
        return dict(ref)
    legacy = cfg.get(legacy_env_field, "")
    if legacy:
        return {"source": "ENV", "name": legacy}
    return {"source": "ENV", "name": ""}


def _resolve_secret_ref(
    ref: Mapping[str, Any],
    request_input: Mapping[str, Any],
) -> str:
    """Read the credential value pointed at by a ``SecretRef``."""
    if not ref:
        return ""
    source = str(ref.get("source", "ENV")).upper()
    name = ref.get("name", "")
    if not name:
        return ""

    if source in ("ENV", "SECRET_SOURCE_UNSPECIFIED", ""):
        return os.environ.get(name, "")

    if source == "HEADER":
        # HTTP headers passed in by the agent via with_request_headers(...)
        # or the _headers= kwarg. Lookup is case-insensitive.
        headers = current_request_headers()
        lowered = {k.lower(): v for k, v in headers.items()}
        return lowered.get(name.lower(), "")

    if source == "PARAMETER":
        return str(request_input.get(name, ""))

    if source == "GCP_SECRET":
        return _read_gcp_secret(name)

    log.warning("auth: unknown SecretRef source=%r — returning empty", source)
    return ""


def _read_gcp_secret(resource_name: str) -> str:
    """Read a Google Secret Manager payload. Returns '' if the client isn't installed."""
    try:
        from google.cloud import secretmanager  # type: ignore
    except ImportError:
        log.warning(
            "auth: google-cloud-secret-manager not installed — cannot resolve %s. "
            "Install with: pip install google-cloud-secret-manager",
            resource_name,
        )
        return ""
    client = secretmanager.SecretManagerServiceClient()
    resp = client.access_secret_version(name=resource_name)
    return resp.payload.data.decode("utf-8")


def _fetch_oauth2_token(
    *,
    client_id: str,
    client_secret: str,
    token_url: str,
    scope: str = "",
) -> dict[str, Any]:
    """Fetch an OAuth2 client-credentials access token (synchronous httpx)."""
    import httpx

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


def _fetch_service_account_token(
    *,
    credentials_ref: Mapping[str, Any],
    scopes: list[str],
    audience: str,
    request_input: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve a GCP service-account JSON key and mint an access/ID token."""
    try:
        from google.auth.transport.requests import Request  # type: ignore
        from google.oauth2 import service_account  # type: ignore
    except ImportError:
        log.warning(
            "auth: google-auth not installed — cannot mint service_account token. "
            "Install with: pip install google-auth"
        )
        return {}

    raw = _resolve_secret_ref(credentials_ref, request_input)
    if not raw:
        return {}

    # raw is either a JSON blob or a filesystem path
    info: dict[str, Any]
    if raw.lstrip().startswith("{"):
        info = json.loads(raw)
    elif os.path.isfile(raw):
        with open(raw) as f:
            info = json.load(f)
    else:
        log.error("auth: service_account credentials not JSON and not a file path")
        return {}

    if audience:
        # ID token (used when calling Cloud Run / IAP / etc.)
        creds = service_account.IDTokenCredentials.from_service_account_info(
            info, target_audience=audience
        )
        creds.refresh(Request())
        return {"type": "bearer", "token": creds.token}

    # OAuth2 access token
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=scopes or ["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(Request())
    return {"type": "bearer", "token": creds.token}


def _fetch_service_agent_token(
    *,
    target_principal: str,
    scopes: list[str],
    audience: str,
) -> dict[str, Any]:
    """Use application default credentials, optionally impersonating a target SA."""
    try:
        import google.auth  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except ImportError:
        log.warning(
            "auth: google-auth not installed — cannot use service_agent auth. "
            "Install with: pip install google-auth"
        )
        return {}

    default_scopes = scopes or ["https://www.googleapis.com/auth/cloud-platform"]
    try:
        source_creds, _ = google.auth.default(scopes=default_scopes)
    except Exception as exc:  # DefaultCredentialsError or similar
        log.warning("auth: no application default credentials available (%s)", exc)
        return {}

    if target_principal:
        try:
            from google.auth import impersonated_credentials  # type: ignore
        except ImportError:
            log.error("auth: google.auth.impersonated_credentials unavailable")
            return {}

        if audience:
            creds = impersonated_credentials.IDTokenCredentials(  # type: ignore[assignment]
                impersonated_credentials.Credentials(
                    source_credentials=source_creds,
                    target_principal=target_principal,
                    target_scopes=default_scopes,
                ),
                target_audience=audience,
            )
        else:
            creds = impersonated_credentials.Credentials(  # type: ignore[assignment]
                source_credentials=source_creds,
                target_principal=target_principal,
                target_scopes=default_scopes,
            )
        creds.refresh(Request())
        return {"type": "bearer", "token": creds.token}

    source_creds.refresh(Request())
    return {"type": "bearer", "token": source_creds.token}
