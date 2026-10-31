import threading
import time
from typing import Any, cast

import httpx
import jwt
from jwt import PyJWK
from jwt.exceptions import PyJWTError

from passport_api.cache import TtlCache
from passport_api.db import get_supabase
from passport_api.errors import APIError
from passport_api.settings import email_domain_allowed, settings

_ALGORITHMS = ["RS256", "ES256"]

# Signing keys change rarely, so they are kept in memory instead of being fetched on every
# request. A token that names a key we do not have triggers one refresh, but never more than
# one per _MIN_REFRESH_SECONDS, so a flood of made-up key ids cannot hammer Supabase.
_JWKS_TTL_SECONDS = 600.0
_JWKS_MIN_REFRESH_SECONDS = 30.0
# If Supabase is unreachable we keep trusting the last good keys for this long.
_JWKS_MAX_STALE_SECONDS = 3600.0

# Admins found in admin_users, remembered briefly so a page that makes several admin requests
# at once checks the table once. Only a "yes" is kept, and an admin write clears it. Removing
# someone from admin_users therefore takes effect within _ADMIN_TTL_SECONDS at the latest.
_ADMIN_TTL_SECONDS = 30.0
_admin_cache: TtlCache[bool] = TtlCache(ttl=_ADMIN_TTL_SECONDS)

_jwks_lock = threading.Lock()
_jwks_keys: list[dict[str, object]] | None = None
_jwks_fetched_at = 0.0


def clear_jwks_cache() -> None:
    global _jwks_keys, _jwks_fetched_at
    with _jwks_lock:
        _jwks_keys = None
        _jwks_fetched_at = 0.0


def _clock() -> float:
    return time.monotonic()


def expected_issuer() -> str:
    """The `iss` claim Supabase puts in every token it signs for this project."""
    base = settings.supabase_url.strip().rstrip("/")
    if not base:
        raise APIError(401, "unauthorized")
    return f"{base}/auth/v1"


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
    if _admin_cache.get(email):
        return email
    response = (
        get_supabase().table("admin_users").select("id").eq("email", email).limit(1).execute()
    )
    rows = response.data
    if not isinstance(rows, list) or not rows:
        raise APIError(403, "admin_not_found")
    _admin_cache.put(email, True)
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
        issuer = expected_issuer()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        jwk = _matching_jwk(kid if isinstance(kid, str) else None)
        payload = jwt.decode(
            token,
            PyJWK.from_dict(cast(dict[str, Any], jwk)).key,
            algorithms=_ALGORITHMS,
            audience="authenticated",
            issuer=issuer,
            options={"require": ["exp", "email", "aud", "iss"]},
        )
    except PyJWTError as exc:
        raise APIError(401, "unauthorized") from exc
    email = payload.get("email")
    if not isinstance(email, str) or email.strip() == "":
        raise APIError(401, "unauthorized")
    return email.strip()


def _find_key(keys: list[dict[str, object]], kid: str) -> dict[str, object] | None:
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


def _usable_keys(payload: dict[str, object]) -> list[dict[str, object]]:
    keys = payload.get("keys")
    if not isinstance(keys, list):
        raise APIError(401, "unauthorized")
    return [cast(dict[str, object], key) for key in keys if isinstance(key, dict)]


def _matching_jwk(kid: str | None) -> dict[str, object]:
    global _jwks_keys, _jwks_fetched_at
    if kid is None:
        raise APIError(401, "unauthorized")
    with _jwks_lock:
        now = _clock()
        age = now - _jwks_fetched_at
        if _jwks_keys is not None and age < _JWKS_TTL_SECONDS:
            found = _find_key(_jwks_keys, kid)
            if found is not None:
                return found
            if age < _JWKS_MIN_REFRESH_SECONDS:
                raise APIError(401, "unauthorized")
        try:
            fresh = _usable_keys(fetch_jwks())
        except APIError:
            # Supabase is down or answered nonsense. Fall back to the last good keys, but
            # only for a limited time.
            if _jwks_keys is None or age > _JWKS_MAX_STALE_SECONDS:
                raise
            fresh = _jwks_keys
        else:
            _jwks_keys = fresh
            _jwks_fetched_at = now
        found = _find_key(fresh, kid)
        if found is None:
            raise APIError(401, "unauthorized")
        return found
