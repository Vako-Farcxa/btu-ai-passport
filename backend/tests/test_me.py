import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from passport_api.main import app

client = TestClient(app)

_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_JWK = json.loads(RSAAlgorithm.to_jwk(_PRIVATE.public_key()))
_PUBLIC_JWK.update({"kid": "test-key", "alg": "RS256", "use": "sig"})


def _token(email: str, *, key: rsa.RSAPrivateKey = _PRIVATE, expired: bool = False) -> str:
    now = int(time.time())
    payload = {
        "aud": "authenticated",
        "email": email,
        "exp": now - 30 if expired else now + 600,
        "sub": "user",
    }
    encoded = jwt.encode(payload, key, algorithm="RS256", headers={"kid": "test-key"})
    assert isinstance(encoded, str)
    return encoded


def _use_test_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    import passport_api.auth as auth

    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": [_PUBLIC_JWK]})


def test_btu_token_returns_only_that_passport_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_test_jwks(monkeypatch)
    response = client.get(
        "/me/passport",
        headers={"Authorization": f"Bearer {_token('demo.student@btu.edu.ge')}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["passport"]["passport_id"] == "BTU-A1B2C3D4E5"
    versions = body["passport"]["versions"]
    assert [version["version"] for version in versions] == [2, 1]
    assert versions[0]["is_current"] is True
    assert versions[1]["is_current"] is False
    assert versions[0]["verification_code"] == "A1B2-C3D4-E5F6-G7H8"
    assert versions[0]["holder_name"] == "Nino Beridze"
    assert versions[0]["skills"] == [
        {"skill": "Machine Learning", "badge": "Stamp", "awarded_on": "2025-06-01"},
    ]
    assert "BTU-V2W3X4Y5Z6" not in response.text
    assert "error.student@btu.edu.ge" not in response.text
    assert "email" not in body["passport"]


def test_unknown_btu_account_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_test_jwks(monkeypatch)
    response = client.get(
        "/me/passport",
        headers={"Authorization": f"Bearer {_token('nobody@btu.edu.ge')}"},
    )
    assert response.status_code == 200
    assert response.json() == {"passport": None}


def test_non_btu_email_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_test_jwks(monkeypatch)
    response = client.get(
        "/me/passport",
        headers={"Authorization": f"Bearer {_token('other@gmail.com')}"},
    )
    assert response.status_code == 403
    assert response.json() == {"code": "domain_not_allowed"}


@pytest.mark.parametrize(
    "header",
    [
        None,
        "Bearer",
        "Bearer not-a-jwt",
        "Basic abc",
    ],
)
def test_missing_or_invalid_bearer_is_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
    header: str | None,
) -> None:
    _use_test_jwks(monkeypatch)
    headers = {} if header is None else {"Authorization": header}
    response = client.get("/me/passport", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized"}


def test_expired_or_wrong_key_is_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_test_jwks(monkeypatch)
    expired = client.get(
        "/me/passport",
        headers={"Authorization": f"Bearer {_token('demo.student@btu.edu.ge', expired=True)}"},
    )
    foreign = client.get(
        "/me/passport",
        headers={
            "Authorization": f"Bearer {_token('demo.student@btu.edu.ge', key=_OTHER)}",
        },
    )
    assert expired.status_code == 401
    assert expired.json() == {"code": "unauthorized"}
    assert foreign.status_code == 401
    assert foreign.json() == {"code": "unauthorized"}
