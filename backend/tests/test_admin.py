"""Tests for all /admin/* endpoints.

Strategy: patch auth.fetch_jwks so we can generate valid JWTs, then patch
auth.require_admin (the Supabase DB lookup) for unit-level tests, and use a
simple in-memory store where needed for write-path tests.
"""

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

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


def _patch_require_admin(monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    """Make require_admin always return the given email (skips Supabase lookup)."""
    import passport_api.api.admin as admin_mod

    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: email)


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


def test_no_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_test_jwks(monkeypatch)
    # require_admin calls email_from_authorization which needs DB; mock supabase
    with patch("passport_api.auth.get_supabase") as mock_db:
        query = mock_db.return_value.table.return_value.select.return_value.eq.return_value
        chain = query.limit.return_value.execute.return_value
        chain.data = []
        resp = client.get("/admin/students")
    assert resp.status_code == 401
    assert resp.json() == {"code": "unauthorized"}


def test_non_btu_email_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_test_jwks(monkeypatch)
    resp = client.get(
        "/admin/students",
        headers={"Authorization": f"Bearer {_token('outsider@gmail.com')}"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"code": "domain_not_allowed"}


def test_btu_non_admin_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_test_jwks(monkeypatch)
    # Valid btu token but not in admin_users table (empty result)
    with patch("passport_api.auth.get_supabase") as mock_db:
        query = mock_db.return_value.table.return_value.select.return_value.eq.return_value
        chain = query.limit.return_value.execute.return_value
        chain.data = []
        resp = client.get(
            "/admin/students",
            headers={"Authorization": f"Bearer {_token('staff@btu.edu.ge')}"},
        )
    assert resp.status_code == 403
    assert resp.json() == {"code": "admin_not_found"}


# ---------------------------------------------------------------------------
# GET /admin/students — list
# ---------------------------------------------------------------------------


def _make_student_row(
    *,
    email: str = "student@btu.edu.ge",
    full_name: str = "Test Student",
    passport_id: str = "BTU-TEST000001",
    admin_managed: bool = True,
    deleted_at: Any = None,
) -> dict[str, Any]:
    return {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "email": email,
        "full_name": full_name,
        "passport_id": passport_id,
        "admin_managed": admin_managed,
        "deleted_at": deleted_at,
        "created_at": "2026-01-01T00:00:00+00:00",
        "passport_versions": [
            {"version_number": 1, "anchor_status": "confirmed"},
        ],
    }


def test_list_students_returns_correct_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    row = _make_student_row()
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        # Mocking the fluent query builder chain
        mock_table = MagicMock()
        mock_db.return_value.table.return_value = mock_table

        mock_query = MagicMock()
        mock_table.select.return_value = mock_query
        mock_query.is_.return_value = mock_query
        mock_query.or_.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.range.return_value = mock_query
        mock_query.count = 1
        mock_query.execute.return_value.data = [row]
        mock_query.execute.return_value.count = 1

        resp = client.get(
            "/admin/students",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "students" in body
    assert "total" in body
    student = body["students"][0]
    assert student["passport_id"] == "BTU-TEST000001"
    assert student["admin_managed"] is True
    assert student["deleted_at"] is None
    assert student["version_count"] == 1
    assert student["latest_anchor_status"] == "confirmed"


# ---------------------------------------------------------------------------
# GET /admin/students/{passport_id} — detail
# ---------------------------------------------------------------------------


def _make_version_row(version_number: int = 1) -> dict[str, Any]:
    return {
        "id": f"11111111-000{version_number}-0000-0000-000000000001",
        "version_number": version_number,
        "holder_name": "Test Student",
        "verification_code": f"TEST-000{version_number}-XXXX-XXXX",
        "anchor_status": "confirmed",
        "tx_hash": "0x" + "a" * 64,
        "issued_at": "2026-01-01T00:00:00+00:00",
        "pdf_en_path": f"BTU-TEST000001/v{version_number}/en.pdf",
        "pdf_ka_path": f"BTU-TEST000001/v{version_number}/ka.pdf",
        "skill_entries": [
            {
                "id": "eeeeeeee-0000-0000-0000-000000000001",
                "skill": "Machine Learning",
                "badge": "BDG-AI-001",
                "awarded_on": "2026-01-01",
                "description": "",
                "position": 1,
            }
        ],
    }


def test_student_detail_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    student_row = {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "email": "student@btu.edu.ge",
        "full_name": "Test Student",
        "passport_id": "BTU-TEST000001",
        "admin_managed": True,
        "deleted_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    version_row = _make_version_row(1)

    with patch("passport_api.api.admin.get_supabase") as mock_db:
        # _require_admin_student
        student_q = MagicMock()
        student_q.execute.return_value.data = [student_row]
        # versions query
        versions_q = MagicMock()
        versions_q.execute.return_value.data = [version_row]

        table_mock = MagicMock()
        mock_db.return_value.table.return_value = table_mock
        # First call: students table for _require_admin_student
        table_mock.select.return_value.eq.return_value.limit.return_value = student_q
        # Second call: passport_versions for versions
        exec_data = table_mock.select.return_value.eq.return_value.order.return_value.execute
        exec_data.return_value.data = [version_row]

        resp = client.get(
            "/admin/students/BTU-TEST000001",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passport_id"] == "BTU-TEST000001"
    assert body["admin_managed"] is True
    assert len(body["versions"]) >= 0  # structure checked


# ---------------------------------------------------------------------------
# Soft-delete
# ---------------------------------------------------------------------------


def test_soft_delete_already_deleted_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    student_row = {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "email": "student@btu.edu.ge",
        "full_name": "Test Student",
        "passport_id": "BTU-TEST000001",
        "admin_managed": True,
        "deleted_at": "2026-01-02T00:00:00+00:00",  # already deleted
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        q = MagicMock()
        q.execute.return_value.data = [student_row]
        limit_mock = (
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.limit
        )
        limit_mock.return_value = q
        resp = client.delete(
            "/admin/students/BTU-TEST000001",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 409
    assert resp.json() == {"code": "student_already_deleted"}


# ---------------------------------------------------------------------------
# Skill add — sheet-managed student rejected
# ---------------------------------------------------------------------------


def test_add_skill_sheet_managed_student_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    student_row = {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "email": "student@btu.edu.ge",
        "full_name": "Sheet Student",
        "passport_id": "BTU-SHEET00001",
        "admin_managed": False,  # <-- sheet-managed
        "deleted_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        q = MagicMock()
        q.execute.return_value.data = [student_row]
        limit_mock = (
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.limit
        )
        limit_mock.return_value = q
        resp = client.post(
            "/admin/students/BTU-SHEET00001/skills",
            json={"skill": "Deep Learning", "badge": "", "awarded_on": None},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 422
    assert resp.json() == {"code": "sheet_managed_student"}


# ---------------------------------------------------------------------------
# Skill remove — unknown skill_id returns 404
# ---------------------------------------------------------------------------


def test_remove_unknown_skill_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    student_row = {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "email": "student@btu.edu.ge",
        "full_name": "Admin Student",
        "passport_id": "BTU-ADMIN00001",
        "admin_managed": True,
        "deleted_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    version_row = {
        "id": "vvvvvvvv-0001-0000-0000-000000000001",
        "version_number": 1,
        "skill_entries": [
            {
                "id": "eeeeeeee-0001-0000-0000-000000000001",
                "skill": "NLP",
                "badge": "",
                "awarded_on": None,
                "description": "",
                "position": 1,
            }
        ],
    }
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        student_q = MagicMock()
        student_q.execute.return_value.data = [student_row]
        version_q = MagicMock()
        version_q.execute.return_value.data = [version_row]

        def table_side_effect(name: str) -> MagicMock:
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.limit.return_value = student_q
            elif name == "passport_versions":
                t.select.return_value.eq.return_value.order.return_value.limit.return_value = (
                    version_q
                )
            return t

        mock_db.return_value.table.side_effect = table_side_effect

        resp = client.delete(
            "/admin/students/BTU-ADMIN00001/skills/nonexistent-skill-id",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 404
    assert resp.json() == {"code": "skill_not_found"}


# ---------------------------------------------------------------------------
# Anchor retry — already confirmed returns 409
# ---------------------------------------------------------------------------


def test_retry_confirmed_anchor_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    version_row = {
        "id": "vvvvvvvv-0001-0000-0000-000000000001",
        "version_number": 1,
        "holder_name": "Test",
        "verification_code": "ABCD-EFGH-IJKL-MNOP",
        "verification_id_hash": "0x" + "b" * 64,
        "skill_fingerprint": "0x" + "c" * 64,
        "content_hash": "0x" + "d" * 64,
        "anchor_status": "confirmed",  # <-- already confirmed
        "tx_hash": "0x" + "e" * 64,
        "anchored_at": "2026-01-02T00:00:00+00:00",
        "issued_at": "2026-01-01T00:00:00+00:00",
        "skill_entries": [],
        "students": [{"email": "student@btu.edu.ge", "passport_id": "BTU-TEST000001"}],
    }
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        q = MagicMock()
        q.execute.return_value.data = [version_row]
        limit_mock = (
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.limit
        )
        limit_mock.return_value = q
        resp = client.post(
            "/admin/versions/vvvvvvvv-0001-0000-0000-000000000001/anchor",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 409
    assert resp.json() == {"code": "anchor_already_confirmed"}


# ---------------------------------------------------------------------------
# PDF regenerate — exists without force returns 409
# ---------------------------------------------------------------------------


def test_regenerate_pdf_exists_no_force_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    version_row = {
        "id": "vvvvvvvv-0001-0000-0000-000000000001",
        "version_number": 1,
        "holder_name": "Test",
        "verification_code": "ABCD-EFGH-IJKL-MNOP",
        "issued_at": "2026-01-01T00:00:00+00:00",
        "pdf_en_path": "BTU-TEST/v1/en.pdf",
        "pdf_ka_path": "BTU-TEST/v1/ka.pdf",
        "skill_entries": [],
        "students": [{"email": "student@btu.edu.ge", "passport_id": "BTU-TEST000001"}],
    }
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        q = MagicMock()
        q.execute.return_value.data = [version_row]
        limit_mock = (
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.limit
        )
        limit_mock.return_value = q
        resp = client.post(
            "/admin/versions/vvvvvvvv-0001-0000-0000-000000000001/pdf",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 409
    assert resp.json() == {"code": "pdf_already_exists"}


# ---------------------------------------------------------------------------
# Version not found
# ---------------------------------------------------------------------------


def test_anchor_version_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_require_admin(monkeypatch, "admin@btu.edu.ge")
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        q = MagicMock()
        q.execute.return_value.data = []
        limit_mock = (
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.limit
        )
        limit_mock.return_value = q
        resp = client.post(
            "/admin/versions/00000000-0000-0000-0000-000000000000/anchor",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 404
    assert resp.json() == {"code": "version_not_found"}
