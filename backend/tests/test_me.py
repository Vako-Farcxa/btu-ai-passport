import json
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from passport_api.main import app
from passport_api.pdf import LocalPdfStorage
from passport_api.settings import settings
from passport_api.store import MemoryStore, StoredVersion

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


def _stored(
    *,
    email: str,
    passport_id: str,
    version: int,
    code: str,
    pdf_en_path: str | None,
    pdf_ka_path: str | None,
) -> StoredVersion:
    return StoredVersion(
        passport_id=passport_id,
        email=email,
        full_name="Nino Beridze",
        version=version,
        holder_name="Nino Beridze",
        verification_code=code,
        anchor_status="pending",
        tx_hash=None,
        issued_at="2025-06-01T00:00:00Z",
        skills=(),
        pdf_en_path=pdf_en_path,
        pdf_ka_path=pdf_ka_path,
    )


def test_owner_downloads_one_language_and_cannot_read_another_student(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_test_jwks(monkeypatch)
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    own_en = "BTU-A1B2C3D4E5/v2/en.pdf"
    own_ka = "BTU-A1B2C3D4E5/v2/ka.pdf"
    other_en = "BTU-V2W3X4Y5Z6/v1/en.pdf"
    storage = LocalPdfStorage(tmp_path)
    storage.put(own_en, b"%PDF-1.4\nowner-en")
    storage.put(own_ka, b"%PDF-1.4\nowner-ka")
    storage.put(other_en, b"%PDF-1.4\nother-student")
    store = MemoryStore(
        (
            _stored(
                email="demo.student@btu.edu.ge",
                passport_id="BTU-A1B2C3D4E5",
                version=2,
                code="A1B2-C3D4-E5F6-G7H8",
                pdf_en_path=own_en,
                pdf_ka_path=own_ka,
            ),
            _stored(
                email="demo.student@btu.edu.ge",
                passport_id="BTU-A1B2C3D4E5",
                version=1,
                code="K9M2-N3P4-Q5R6-S7T8",
                pdf_en_path=None,
                pdf_ka_path=None,
            ),
            _stored(
                email="error.student@btu.edu.ge",
                passport_id="BTU-V2W3X4Y5Z6",
                version=1,
                code="V2W3-X4Y5-Z6A7-B8C9",
                pdf_en_path=other_en,
                pdf_ka_path=other_en,
            ),
        )
    )
    monkeypatch.setattr("passport_api.api.me.get_store", lambda: store)
    headers = {"Authorization": f"Bearer {_token('demo.student@btu.edu.ge')}"}
    english = client.get("/me/passport/versions/2/pdf?lang=en", headers=headers)
    georgian = client.get("/me/passport/versions/2/pdf?lang=ka", headers=headers)
    missing = client.get("/me/passport/versions/1/pdf?lang=en", headers=headers)
    other = client.get(
        "/me/passport/versions/2/pdf?lang=en",
        headers={"Authorization": f"Bearer {_token('error.student@btu.edu.ge')}"},
    )
    refused = client.get(
        "/me/passport/versions/2/pdf?lang=en",
        headers={"Authorization": f"Bearer {_token('other@gmail.com')}"},
    )
    anonymous = client.get("/me/passport/versions/2/pdf?lang=en")
    assert english.status_code == 200
    assert english.headers["content-type"].startswith("application/pdf")
    assert english.content == b"%PDF-1.4\nowner-en"
    assert georgian.status_code == 200
    assert georgian.content == b"%PDF-1.4\nowner-ka"
    assert b"other-student" not in english.content
    assert missing.status_code == 409
    assert missing.json() == {"code": "pdf_not_ready"}
    assert other.status_code == 404
    assert other.json() == {"code": "version_not_found"}
    assert refused.status_code == 403
    assert refused.json() == {"code": "domain_not_allowed"}
    assert anonymous.status_code == 401
    assert anonymous.json() == {"code": "unauthorized"}
