"""Token checks in passport_api.auth: issuer, audience and the signing-key cache."""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import passport_api.auth as auth
from passport_api.errors import APIError
from passport_api.settings import settings

ISSUER = "https://test-project.supabase.co/auth/v1"
EMAIL = "student@btu.edu.ge"


def _key_pair(kid: str) -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return private, jwk


_KEY, _JWK = _key_pair("key-1")
_KEY2, _JWK2 = _key_pair("key-2")


def _token(
    *,
    key: rsa.RSAPrivateKey = _KEY,
    kid: str = "key-1",
    drop: tuple[str, ...] = (),
    **overrides: object,
) -> str:
    payload: dict[str, object] = {
        "aud": "authenticated",
        "iss": ISSUER,
        "email": EMAIL,
        "exp": int(time.time()) + 600,
        "sub": "user",
    }
    payload.update(overrides)
    for name in drop:
        payload.pop(name)
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def _check(token: str) -> str:
    return auth.email_from_authorization(f"Bearer {token}")


class Jwks:
    """A fake Supabase JWKS endpoint that counts calls and has a controllable clock."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        self.keys: list[dict[str, object]] = [_JWK]
        self.down = False
        self.now = 1000.0
        monkeypatch.setattr(auth, "fetch_jwks", self._fetch)
        monkeypatch.setattr(auth, "_clock", lambda: self.now)

    def _fetch(self) -> dict[str, object]:
        self.calls += 1
        if self.down:
            raise APIError(401, "unauthorized")
        return {"keys": list(self.keys)}


@pytest.fixture
def jwks(monkeypatch: pytest.MonkeyPatch) -> Jwks:
    return Jwks(monkeypatch)


def test_a_token_from_this_project_is_accepted(jwks: Jwks) -> None:
    assert _check(_token()) == EMAIL


def test_a_trailing_slash_on_the_project_url_does_not_matter(
    jwks: Jwks, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://test-project.supabase.co/")
    assert _check(_token()) == EMAIL


@pytest.mark.parametrize(
    "issuer",
    [
        "https://other-project.supabase.co/auth/v1",
        "https://test-project.supabase.co",
        "https://test-project.supabase.co/auth/v1/",
        "https://evil.example/auth/v1",
        "",
    ],
)
def test_a_token_from_another_issuer_is_refused(jwks: Jwks, issuer: str) -> None:
    with pytest.raises(APIError) as caught:
        _check(_token(iss=issuer))
    assert caught.value.status_code == 401


def test_a_token_without_an_issuer_is_refused(jwks: Jwks) -> None:
    with pytest.raises(APIError) as caught:
        _check(_token(drop=("iss",)))
    assert caught.value.status_code == 401


def test_a_token_without_an_audience_is_refused(jwks: Jwks) -> None:
    with pytest.raises(APIError) as caught:
        _check(_token(drop=("aud",)))
    assert caught.value.status_code == 401


def test_a_token_for_another_audience_is_refused(jwks: Jwks) -> None:
    with pytest.raises(APIError) as caught:
        _check(_token(aud="anon"))
    assert caught.value.status_code == 401


def test_nothing_is_accepted_when_the_project_url_is_not_configured(
    jwks: Jwks, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    with pytest.raises(APIError) as caught:
        _check(_token())
    assert caught.value.status_code == 401
    assert jwks.calls == 0


def test_keys_are_fetched_once_for_many_requests(jwks: Jwks) -> None:
    for _ in range(25):
        assert _check(_token()) == EMAIL
    assert jwks.calls == 1


def test_keys_are_fetched_again_after_the_cache_expires(jwks: Jwks) -> None:
    _check(_token())
    jwks.now += auth._JWKS_TTL_SECONDS - 1
    _check(_token())
    assert jwks.calls == 1
    jwks.now += 2
    _check(_token())
    assert jwks.calls == 2


def test_a_rotated_key_is_picked_up_with_one_refresh(jwks: Jwks) -> None:
    _check(_token())
    jwks.keys = [_JWK, _JWK2]
    jwks.now += auth._JWKS_MIN_REFRESH_SECONDS + 1
    assert _check(_token(key=_KEY2, kid="key-2")) == EMAIL
    assert jwks.calls == 2


def test_made_up_key_ids_cannot_trigger_a_refresh_flood(jwks: Jwks) -> None:
    _check(_token())
    for index in range(20):
        with pytest.raises(APIError):
            _check(_token(kid=f"made-up-{index}"))
    assert jwks.calls == 1
    # After the cool-down one unknown key id refreshes once, then the cool-down applies again.
    jwks.now += auth._JWKS_MIN_REFRESH_SECONDS + 1
    for index in range(5):
        with pytest.raises(APIError):
            _check(_token(kid=f"still-made-up-{index}"))
    assert jwks.calls == 2


def test_a_token_signed_by_a_different_key_with_a_known_kid_is_refused(jwks: Jwks) -> None:
    with pytest.raises(APIError) as caught:
        _check(_token(key=_KEY2, kid="key-1"))
    assert caught.value.status_code == 401


def test_a_token_without_a_key_id_is_refused(jwks: Jwks) -> None:
    payload = {"aud": "authenticated", "iss": ISSUER, "email": EMAIL, "exp": int(time.time()) + 60}
    with pytest.raises(APIError):
        _check(jwt.encode(payload, _KEY, algorithm="RS256"))


def test_last_good_keys_keep_working_while_supabase_is_down(jwks: Jwks) -> None:
    _check(_token())
    jwks.down = True
    jwks.now += auth._JWKS_TTL_SECONDS + 5
    assert _check(_token()) == EMAIL
    assert jwks.calls == 2


def test_stale_keys_are_dropped_after_the_grace_period(jwks: Jwks) -> None:
    _check(_token())
    jwks.down = True
    jwks.now += auth._JWKS_MAX_STALE_SECONDS + 5
    with pytest.raises(APIError) as caught:
        _check(_token())
    assert caught.value.status_code == 401


def test_nothing_is_accepted_when_the_keys_were_never_fetched_and_supabase_is_down(
    jwks: Jwks,
) -> None:
    jwks.down = True
    with pytest.raises(APIError) as caught:
        _check(_token())
    assert caught.value.status_code == 401


def test_a_garbage_key_list_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": "nope"})
    with pytest.raises(APIError) as caught:
        _check(_token())
    assert caught.value.status_code == 401
