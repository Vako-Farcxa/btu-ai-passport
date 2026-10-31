"""Every API response carries the basic browser security headers."""

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

from passport_api.main import app, create_app
from passport_api.security_headers import SecurityHeadersMiddleware

client = TestClient(app)

EXPECTED = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def _check(headers: Mapping[str, str]) -> None:
    got = {key.lower(): value for key, value in headers.items()}
    for name, value in EXPECTED.items():
        assert got[name] == value
    assert got["strict-transport-security"].startswith("max-age=31536000")
    assert "frame-ancestors 'none'" in got["content-security-policy"]
    assert "default-src 'none'" in got["content-security-policy"]
    assert "camera=()" in got["permissions-policy"]


def test_health_has_the_headers() -> None:
    _check(client.get("/health").headers)


def test_error_and_validation_responses_have_them_too() -> None:
    _check(client.post("/verify", json={}).headers)
    _check(client.get("/admin/me").headers)
    _check(client.get("/no-such-route").headers)


def test_a_429_has_them_too(monkeypatch: pytest.MonkeyPatch) -> None:
    from passport_api.settings import settings

    monkeypatch.setattr(settings, "rate_limit_verify_per_minute", 1)
    client.post("/verify", json={"code": "A1B2-C3D4-E5F6-G7H8"})
    blocked = client.post("/verify", json={"code": "A1B2-C3D4-E5F6-G7H8"})
    assert blocked.status_code == 429
    _check(blocked.headers)


def test_cors_preflight_has_them_and_only_allows_the_known_origin() -> None:
    ok = client.options(
        "/verify",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in ok.headers
    _check(ok.headers)

    evil = client.options(
        "/verify",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in evil.headers


def test_cors_refuses_methods_and_headers_the_app_never_uses() -> None:
    odd_header = client.options(
        "/verify",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-anything",
        },
    )
    assert odd_header.status_code == 400
    odd_method = client.options(
        "/verify",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "PUT"},
    )
    assert odd_method.status_code == 400


def test_the_docs_page_keeps_working_when_turned_on() -> None:
    docs_app = create_app(enable_docs=True)
    docs_app.add_middleware(SecurityHeadersMiddleware, docs_paths=("/docs", "/openapi.json"))
    docs_client = TestClient(docs_app)
    page = docs_client.get("/docs")
    assert page.status_code == 200
    assert "content-security-policy" not in page.headers
    assert page.headers["x-content-type-options"] == "nosniff"
