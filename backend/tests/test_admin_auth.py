"""Every /admin route needs a valid Supabase JWT whose email is in admin_users."""

import json
import re
import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

import passport_api.auth as auth
from passport_api.main import app
from passport_api.settings import settings

client = TestClient(app)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update({"kid": "test-key", "alg": "RS256", "use": "sig"})


def _token(email: str) -> str:
    payload = {
        "aud": "authenticated",
        "email": email,
        "exp": int(time.time()) + 600,
        "sub": "user",
    }
    return jwt.encode(payload, _KEY, algorithm="RS256", headers={"kid": "test-key"})


def _admin_routes() -> list[tuple[str, str]]:
    # The OpenAPI document lists every mounted route, so a new admin route that forgets
    # the guard is picked up here automatically.
    routes: list[tuple[str, str]] = []
    for path, operations in app.openapi()["paths"].items():
        if path.startswith("/admin"):
            for method in sorted(operations):
                routes.append((method.upper(), re.sub(r"\{[^}]+\}", "x", path)))
    return routes


ROUTES = _admin_routes()


@pytest.fixture(autouse=True)
def _jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": [_JWK]})
    monkeypatch.setattr(settings, "allowed_email_domains", "btu.edu.ge")


def test_the_route_list_is_not_empty() -> None:
    paths = {path for _, path in ROUTES}
    assert {
        "/admin/me",
        "/admin/students",
        "/admin/skills",
        "/admin/awards",
        "/admin/sync",
    } <= paths
    assert len(ROUTES) >= 15


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_no_token_is_401(method: str, path: str) -> None:
    response = client.request(method, path, json={})
    assert response.status_code == 401, (method, path)
    assert response.json() == {"code": "unauthorized"}


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_demo_admin_token_is_401_by_default(method: str, path: str) -> None:
    assert settings.demo_mode is False
    response = client.request(method, path, json={}, headers={"Authorization": "Bearer demo-admin"})
    assert response.status_code == 401, (method, path)


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_demo_admin_token_is_401_even_when_supabase_is_not_configured(
    method: str, path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    response = client.request(method, path, json={}, headers={"Authorization": "Bearer demo-admin"})
    assert response.status_code == 401, (method, path)


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_bad_signature_is_401(method: str, path: str) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {"aud": "authenticated", "email": "admin@btu.edu.ge", "exp": int(time.time()) + 600},
        other,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    response = client.request(method, path, json={}, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401, (method, path)


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_other_domain_is_403(method: str, path: str) -> None:
    response = client.request(
        method, path, json={}, headers={"Authorization": f"Bearer {_token('someone@gmail.com')}"}
    )
    assert response.status_code == 403, (method, path)
    assert response.json() == {"code": "domain_not_allowed"}


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_btu_user_who_is_not_an_admin_is_403(method: str, path: str) -> None:
    with patch("passport_api.auth.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value.eq.return_value
        query.limit.return_value.execute.return_value.data = []
        response = client.request(
            method, path, json={}, headers={"Authorization": f"Bearer {_token('staff@btu.edu.ge')}"}
        )
    assert response.status_code == 403, (method, path)
    assert response.json() == {"code": "admin_not_found"}


def test_me_confirms_a_listed_admin() -> None:
    with patch("passport_api.auth.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value.eq.return_value
        query.limit.return_value.execute.return_value.data = [{"id": "1"}]
        response = client.get(
            "/admin/me", headers={"Authorization": f"Bearer {_token('Admin@btu.edu.ge')}"}
        )
    assert response.status_code == 200
    assert response.json() == {"email": "admin@btu.edu.ge"}


def test_demo_admin_works_only_when_demo_mode_is_explicitly_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "demo_mode", True)
    response = client.get("/admin/me", headers={"Authorization": "Bearer demo-admin"})
    assert response.status_code == 200
    assert response.json() == {"email": "admin@btu.edu.ge"}


def test_demo_mode_defaults_to_off() -> None:
    from passport_api.settings import Settings

    assert Settings(_env_file=None).demo_mode is False
