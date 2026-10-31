"""Light in-memory rate limits: the counter, the client address, and the three routes."""

import json
import time
from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from starlette.requests import Request

import passport_api.api.admin as admin_mod
import passport_api.auth as auth
from passport_api.flags import MemoryFlagStore, get_flag_store
from passport_api.main import app
from passport_api.ratelimit import RateLimits, client_ip
from passport_api.settings import settings

client = TestClient(app)

VALID = "A1B2-C3D4-E5F6-G7H8"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update({"kid": "test-key", "alg": "RS256", "use": "sig"})


def _bearer(email: str) -> dict[str, str]:
    payload = {
        "aud": "authenticated",
        "iss": "https://test-project.supabase.co/auth/v1",
        "email": email,
        "exp": int(time.time()) + 600,
        "sub": "user",
    }
    token = jwt.encode(payload, _KEY, algorithm="RS256", headers={"kid": "test-key"})
    return {"Authorization": f"Bearer {token}"}


def _request(
    forwarded: list[str], peer: str | None = "10.0.0.9", extra: dict[str, str] | None = None
) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    headers += [(name.encode(), value.encode()) for name, value in (extra or {}).items()]
    scope: dict[str, object] = {
        "type": "http",
        "headers": headers,
        "client": None if peer is None else (peer, 5000),
    }
    return Request(scope)


# -- the counter --------------------------------------------------------------


def test_allows_up_to_the_limit_then_says_how_long_to_wait() -> None:
    limiter = RateLimits()
    for second in range(3):
        assert limiter.check("b", "k", 3, now=100.0 + second) is None
    assert limiter.check("b", "k", 3, now=103.0) == 57  # the first hit leaves at 160


def test_the_window_slides() -> None:
    limiter = RateLimits()
    for _ in range(3):
        assert limiter.check("b", "k", 3, now=100.0) is None
    assert limiter.check("b", "k", 3, now=159.0) == 1
    assert limiter.check("b", "k", 3, now=160.5) is None


def test_refused_requests_are_not_counted() -> None:
    limiter = RateLimits()
    assert limiter.check("b", "k", 1, now=100.0) is None
    for _ in range(50):
        assert limiter.check("b", "k", 1, now=110.0) is not None
    # Waiting the original 60 seconds is enough, hammering did not extend it.
    assert limiter.check("b", "k", 1, now=160.5) is None


def test_keys_and_buckets_are_separate() -> None:
    limiter = RateLimits()
    assert limiter.check("b", "one", 1, now=1.0) is None
    assert limiter.check("b", "two", 1, now=1.0) is None
    assert limiter.check("other", "one", 1, now=1.0) is None
    assert limiter.check("b", "one", 1, now=2.0) is not None


def test_a_limit_of_zero_means_off() -> None:
    limiter = RateLimits()
    for _ in range(100):
        assert limiter.check("b", "k", 0, now=1.0) is None


def test_memory_is_bounded() -> None:
    limiter = RateLimits(max_keys=100)
    for index in range(1000):
        limiter.check("b", f"ip-{index}", 5, now=1.0)
    assert len(limiter._hits) == 100  # noqa: SLF001


# -- which address counts -----------------------------------------------------


def test_without_trusted_proxies_the_header_is_ignored() -> None:
    request = _request(["1.1.1.1"], peer="9.9.9.9")
    assert client_ip(request, 0) == "9.9.9.9"


def test_takes_the_entry_the_trusted_proxies_vouch_for() -> None:
    # A forged first entry, then the real client, then two proxies added by the platform.
    request = _request(["6.6.6.6, 203.0.113.7, 172.70.1.1, 10.1.2.3"])
    assert client_ip(request, 3) == "203.0.113.7"
    assert client_ip(request, 1) == "10.1.2.3"


def test_a_forged_left_side_cannot_change_the_key() -> None:
    first = _request(["1.1.1.1, 203.0.113.7, 172.70.1.1, 10.1.2.3"])
    second = _request(["2.2.2.2, 3.3.3.3, 203.0.113.7, 172.70.1.1, 10.1.2.3"])
    assert client_ip(first, 3) == client_ip(second, 3) == "203.0.113.7"


def test_several_header_lines_count_as_one_list() -> None:
    request = _request(["6.6.6.6", "203.0.113.7, 172.70.1.1, 10.1.2.3"])
    assert client_ip(request, 3) == "203.0.113.7"


def test_a_short_chain_falls_back_to_its_first_entry_then_the_peer() -> None:
    assert client_ip(_request(["203.0.113.7"]), 3) == "203.0.113.7"
    assert client_ip(_request([]), 3) == "10.0.0.9"
    assert client_ip(_request([], peer=None), 3) == "unknown"


def test_junk_in_the_header_falls_back_to_the_peer() -> None:
    assert client_ip(_request(["not-an-ip, also-junk"]), 1) == "10.0.0.9"


def test_cloudflare_header_wins_over_any_forwarded_chain() -> None:
    # A longer chain than TRUSTED_PROXY_HOPS expects would pick a rotating Cloudflare edge
    # address from the right; the Cloudflare header does not depend on the chain length.
    chain = ["203.0.113.7, 172.70.1.1, 10.1.2.3, 10.4.5.6"]
    request = _request(chain, extra={"cf-connecting-ip": "203.0.113.7"})
    assert client_ip(request, 3) == "203.0.113.7"
    assert client_ip(_request(chain), 3) == "172.70.1.1"  # the old behaviour, now the fallback


def test_cloudflare_header_is_stable_while_the_edge_address_rotates() -> None:
    first = _request(
        ["203.0.113.7, 172.70.1.1, 10.1.2.3, 10.4.5.6"], extra={"cf-connecting-ip": "203.0.113.7"}
    )
    second = _request(
        ["203.0.113.7, 104.22.17.40, 10.9.9.9, 10.8.8.8"], extra={"cf-connecting-ip": "203.0.113.7"}
    )
    assert client_ip(first, 3) == client_ip(second, 3) == "203.0.113.7"


def test_true_client_ip_is_used_when_the_cloudflare_header_is_missing() -> None:
    request = _request(["1.1.1.1, 2.2.2.2"], extra={"true-client-ip": "203.0.113.8"})
    assert client_ip(request, 3) == "203.0.113.8"


def test_a_junk_cloudflare_header_falls_back_to_the_chain() -> None:
    request = _request(["203.0.113.7, 172.70.1.1"], extra={"cf-connecting-ip": "nonsense"})
    assert client_ip(request, 2) == "203.0.113.7"


def test_cloudflare_header_is_ignored_when_no_proxy_is_trusted() -> None:
    request = _request([], peer="9.9.9.9", extra={"cf-connecting-ip": "1.1.1.1"})
    assert client_ip(request, 0) == "9.9.9.9"


def test_cloudflare_ipv6_visitors_share_a_bucket_per_64() -> None:
    one = _request([], extra={"cf-connecting-ip": "2001:db8:1:2:aaaa:bbbb:cccc:1"})
    other = _request([], extra={"cf-connecting-ip": "2001:db8:1:2:1111:2222:3333:4"})
    assert client_ip(one, 3) == client_ip(other, 3) == "2001:db8:1:2::"


def test_verify_limit_follows_the_cloudflare_header_not_the_chain_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_hops", 3)
    monkeypatch.setattr(settings, "rate_limit_verify_per_minute", 2)

    def verify(edge: str) -> int:
        headers = {
            "CF-Connecting-IP": "203.0.113.1",
            # Longer than expected and with a different edge address on every request.
            "X-Forwarded-For": f"203.0.113.1, {edge}, 10.0.0.1, 10.0.0.2",
        }
        return int(client.post("/verify", json={"code": VALID}, headers=headers).status_code)

    assert [verify(f"104.22.17.{n}") for n in range(3)] == [200, 200, 429]


def test_ipv6_clients_share_a_bucket_per_64() -> None:
    one = _request(["2001:db8:1:2:aaaa:bbbb:cccc:1"])
    other = _request(["2001:db8:1:2:1111:2222:3333:4"])
    assert client_ip(one, 1) == client_ip(other, 1) == "2001:db8:1:2::"


# -- POST /verify -------------------------------------------------------------


def test_verify_is_limited_per_ip_with_retry_after() -> None:
    for _ in range(30):
        assert client.post("/verify", json={"code": VALID}).status_code == 200
    blocked = client.post("/verify", json={"code": VALID})
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "rate_limited"}
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60


def test_verify_limit_follows_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_verify_per_minute", 2)
    assert client.post("/verify", json={"code": VALID}).status_code == 200
    assert client.post("/verify", json={"code": VALID}).status_code == 200
    assert client.post("/verify", json={"code": VALID}).status_code == 429


def test_verify_limit_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_verify_per_minute", 1)
    for _ in range(5):
        assert client.post("/verify", json={"code": VALID}).status_code == 200


def test_bad_input_counts_too() -> None:
    for _ in range(30):
        assert client.post("/verify", json={}).status_code == 422
    assert client.post("/verify", json={}).status_code == 429


def test_each_client_behind_the_proxy_has_their_own_verify_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    monkeypatch.setattr(settings, "rate_limit_verify_per_minute", 2)

    def verify(client_address: str, forged: str = "") -> int:
        chain = f"{forged}{client_address}, 172.70.1.1"
        response = client.post("/verify", json={"code": VALID}, headers={"X-Forwarded-For": chain})
        return int(response.status_code)

    assert [verify("203.0.113.1") for _ in range(3)] == [200, 200, 429]
    # Another visitor is not affected.
    assert verify("203.0.113.2") == 200
    # Making up a different left side does not open a new bucket.
    assert verify("203.0.113.1", forged="9.9.9.9, ") == 429


def test_forwarded_header_is_ignored_when_no_proxy_is_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limit_verify_per_minute", 1)
    assert (
        client.post(
            "/verify", json={"code": VALID}, headers={"X-Forwarded-For": "1.1.1.1"}
        ).status_code
        == 200
    )
    again = client.post("/verify", json={"code": VALID}, headers={"X-Forwarded-For": "2.2.2.2"})
    assert again.status_code == 429


def test_the_429_can_be_read_by_the_frontend_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_verify_per_minute", 1)
    origin = {"Origin": "http://localhost:3000"}
    client.post("/verify", json={"code": VALID}, headers=origin)
    blocked = client.post("/verify", json={"code": VALID}, headers=origin)
    assert blocked.status_code == 429
    assert blocked.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "retry-after" in blocked.headers["access-control-expose-headers"].lower()


# -- POST /flags and the admin writes -----------------------------------------


@pytest.fixture
def flag_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[MemoryFlagStore]:
    store = MemoryFlagStore()
    app.dependency_overrides[get_flag_store] = lambda: store
    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": [_JWK]})
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    yield store
    app.dependency_overrides.clear()


def _post_flag(who: str) -> int:
    body = {"version": 99, "comment": "This version is missing a skill I earned."}
    return int(client.post("/flags", headers=_bearer(who), json=body).status_code)


def test_flags_are_limited_per_student(flag_env: MemoryFlagStore) -> None:
    # Version 99 does not exist, so each try is a 404, but it still counts.
    assert [_post_flag("demo.student@btu.edu.ge") for _ in range(5)] == [404] * 5
    blocked = client.post(
        "/flags",
        headers=_bearer("demo.student@btu.edu.ge"),
        json={"version": 99, "comment": "This version is missing a skill I earned."},
    )
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "rate_limited"}
    assert int(blocked.headers["Retry-After"]) >= 1
    # Another student is not affected.
    assert _post_flag("error.student@btu.edu.ge") == 404


def test_flags_without_a_token_are_not_counted(flag_env: MemoryFlagStore) -> None:
    body = {"version": 1, "comment": "This version is missing a skill I earned."}
    for _ in range(10):
        assert client.post("/flags", json=body).status_code == 401


def test_admin_writes_are_limited_per_admin_but_reads_are_not(
    flag_env: MemoryFlagStore,
) -> None:
    headers = {"Authorization": "Bearer admin"}
    for _ in range(60):
        assert client.get("/admin/flags", headers=headers).status_code == 200
    patch = {"status": "resolved", "admin_note": "Fixed."}
    for _ in range(30):
        # No such flag: 404, but the write was counted.
        assert client.patch("/admin/flags/nope", headers=headers, json=patch).status_code == 404
    blocked = client.patch("/admin/flags/nope", headers=headers, json=patch)
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "rate_limited"}
    assert int(blocked.headers["Retry-After"]) >= 1
    # Reads still work for the same admin.
    assert client.get("/admin/flags", headers=headers).status_code == 200


def test_admin_write_limit_is_per_admin(
    flag_env: MemoryFlagStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_admin_writes_per_minute", 1)
    patch = {"status": "resolved", "admin_note": "Fixed."}
    headers = {"Authorization": "Bearer admin"}
    assert client.patch("/admin/flags/x", headers=headers, json=patch).status_code == 404
    assert client.patch("/admin/flags/x", headers=headers, json=patch).status_code == 429
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "second.admin@btu.edu.ge")
    assert client.patch("/admin/flags/x", headers=headers, json=patch).status_code == 404


def test_unauthenticated_admin_writes_are_refused_before_counting(
    flag_env: MemoryFlagStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # real guard again: no token, no admin
    for _ in range(40):
        assert client.patch("/admin/flags/x", json={"status": "resolved"}).status_code == 401


def test_every_admin_write_route_carries_the_limit() -> None:
    """A new /admin write route that skips the shared dependencies fails here."""
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if path.startswith("/admin") and methods & {"POST", "PUT", "PATCH", "DELETE"}:
            names = {
                dependency.call.__name__
                for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
                if dependency.call is not None
            }
            assert "admin_write_limit" in names, path
