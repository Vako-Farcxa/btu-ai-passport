from typing import Any, cast

import httpx
import jwt
from jwt import PyJWK
from jwt.exceptions import PyJWTError

from passport_api.db import get_supabase
from passport_api.errors import APIError
from passport_api.settings import email_domain_allowed, settings

_ALGORITHMS = ["RS256", "ES256"]


def fetch_jwks() -> dict[str, object]:
    base = settings.supabase_url.rstrip("/")
    if not base:
        raise APIError(401, "unauthorized")
    try:
        response = httpx.get(f"{base}/auth/v1/.well-known/jwks.json", timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise APIError(401, "unauthorized") from exc
    payload = response.json()
    if not isinstance(payload, dict):
        raise APIError(401, "unauthorized")
    return cast(dict[str, object], payload)


def email_from_authorization(authorization: str | None) -> str:
    token = _bearer_token(authorization)
    email = _verified_email(token)
    if not email_domain_allowed(email):
        raise APIError(403, "domain_not_allowed")
    return email.strip().lower()


def require_admin(authorization: str | None) -> str:
    """Return the admin's email or raise APIError.

    Checks:
    1. Valid Supabase JWT with a btu.edu.ge email (reuses email_from_authorization).
    2. Email is present in the admin_users table.
    The 'demo-admin' token is accepted only when DEMO_MODE is explicitly turned on, which
    defaults to off. Whether Supabase is configured has no say in it.
    """
    token = _bearer_token(authorization)
    if token == "demo-admin" and settings.demo_mode:  # noqa: S105
        return "admin@btu.edu.ge"
    email = email_from_authorization(authorization)
    response = (
        get_supabase().table("admin_users").select("id").eq("email", email).limit(1).execute()
    )
    rows = response.data
    if not isinstance(rows, list) or not rows:
        raise APIError(403, "admin_not_found")
    return email


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise APIError(401, "unauthorized")
    scheme, _, rest = authorization.partition(" ")
    if scheme.lower() != "bearer" or rest.strip() == "":
        raise APIError(401, "unauthorized")
    return rest.strip()


def _verified_email(token: str) -> str:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        jwk = _matching_jwk(kid if isinstance(kid, str) else None)
        payload = jwt.decode(
            token,
            PyJWK.from_dict(cast(dict[str, Any], jwk)).key,
            algorithms=_ALGORITHMS,
            audience="authenticated",
            options={"require": ["exp", "email"]},
        )
    except PyJWTError as exc:
        raise APIError(401, "unauthorized") from exc
    email = payload.get("email")
    if not isinstance(email, str) or email.strip() == "":
        raise APIError(401, "unauthorized")
    return email.strip()


def _matching_jwk(kid: str | None) -> dict[str, object]:
    keys = fetch_jwks().get("keys")
    if not isinstance(keys, list) or kid is None:
        raise APIError(401, "unauthorized")
    for key in keys:
        if isinstance(key, dict) and key.get("kid") == kid:
            return cast(dict[str, object], key)
    raise APIError(401, "unauthorized")
