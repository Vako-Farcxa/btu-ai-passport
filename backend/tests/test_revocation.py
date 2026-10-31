"""Revocation: archived students and revoked versions are never shown as valid."""

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

import passport_api.api.admin as admin_mod
import passport_api.auth as auth
from passport_api.demo_data import DEMO_VERSIONS
from passport_api.flags import MemoryFlagStore, get_flag_store
from passport_api.main import app
from passport_api.pdf import LocalPdfStorage
from passport_api.settings import settings
from passport_api.store import MemoryStore, StoredVersion
from passport_api.supabase_store import SupabaseStore
from passport_api.verify import verify_code

client = TestClient(app)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update({"kid": "test-key", "alg": "RS256", "use": "sig"})

STUDENT = "demo.student@btu.edu.ge"
LATEST_CODE = "A1B2-C3D4-E5F6-G7H8"
OLDER_CODE = "K9M2-N3P4-Q5R6-S7T8"
ARCHIVED_AT = "2026-10-30T10:00:00+00:00"
REVOKED_AT = "2026-10-29T08:30:00+00:00"


def _headers(email: str = STUDENT) -> dict[str, str]:
    payload = {
        "aud": "authenticated",
        "iss": "https://test-project.supabase.co/auth/v1",
        "email": email,
        "exp": int(time.time()) + 600,
        "sub": "user",
    }
    token = jwt.encode(payload, _KEY, algorithm="RS256", headers={"kid": "test-key"})
    return {"Authorization": f"Bearer {token}"}


def _use_store(monkeypatch: pytest.MonkeyPatch, versions: tuple[StoredVersion, ...]) -> MemoryStore:
    store = MemoryStore(versions)
    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": [_JWK]})
    monkeypatch.setattr("passport_api.api.verify.get_store", lambda: store)
    monkeypatch.setattr("passport_api.api.me.get_store", lambda: store)
    monkeypatch.setattr("passport_api.api.flags.get_store", lambda: store)
    flags = MemoryFlagStore()
    app.dependency_overrides[get_flag_store] = lambda: flags
    return store


@pytest.fixture(autouse=True)
def clean_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


def _archived() -> tuple[StoredVersion, ...]:
    demo = [v for v in DEMO_VERSIONS if v.email == STUDENT]
    return tuple(replace(v, student_archived_at=ARCHIVED_AT) for v in demo)


def _one_version_revoked() -> tuple[StoredVersion, ...]:
    return tuple(
        replace(v, version_revoked_at=REVOKED_AT) if v.version == 1 else v
        for v in DEMO_VERSIONS
        if v.email == STUDENT
    )


# --- the model ---------------------------------------------------------------------------


def test_revoked_at_is_none_for_a_version_in_good_standing() -> None:
    assert DEMO_VERSIONS[0].revoked_at is None


def test_revoked_at_uses_the_earliest_of_version_and_student_dates() -> None:
    both = replace(DEMO_VERSIONS[0], version_revoked_at=REVOKED_AT, student_archived_at=ARCHIVED_AT)
    assert both.revoked_at == REVOKED_AT
    later_version = replace(
        DEMO_VERSIONS[0],
        version_revoked_at="2026-11-01T00:00:00Z",
        student_archived_at=ARCHIVED_AT,
    )
    assert later_version.revoked_at == ARCHIVED_AT


def test_revoked_at_compares_real_times_across_formats() -> None:
    mixed = replace(
        DEMO_VERSIONS[0],
        version_revoked_at="2026-10-30T09:00:00Z",
        student_archived_at="2026-10-30T10:30:00+03:00",
    )
    # 10:30 at +03:00 is 07:30 UTC, which is earlier than 09:00 UTC.
    assert mixed.revoked_at == "2026-10-30T10:30:00+03:00"


# --- verify ------------------------------------------------------------------------------


def test_verify_shows_revoked_for_every_version_of_an_archived_student(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_store(monkeypatch, _archived())
    for code in (LATEST_CODE, OLDER_CODE):
        response = client.post("/verify", json={"code": code})
        assert response.status_code == 200
        assert response.json() == {"outcome": "revoked", "revoked_at": ARCHIVED_AT}


def test_verify_revoked_leaks_no_personal_data(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_store(monkeypatch, _archived())
    text = client.post("/verify", json={"code": LATEST_CODE}).text
    for secret in ("Nino", "Beridze", "Machine Learning", "polygonscan", "tx_url", "skills"):
        assert secret not in text


def test_verify_revokes_one_version_and_leaves_the_others_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_store(monkeypatch, _one_version_revoked())
    older = client.post("/verify", json={"code": OLDER_CODE}).json()
    latest = client.post("/verify", json={"code": LATEST_CODE}).json()
    assert older == {"outcome": "revoked", "revoked_at": REVOKED_AT}
    assert latest["outcome"] == "valid"


def test_revocation_outranks_a_pending_anchor() -> None:
    pending = replace(
        DEMO_VERSIONS[0], anchor_status="pending", tx_hash=None, version_revoked_at=REVOKED_AT
    )
    result = verify_code(MemoryStore([pending]), pending.verification_code)
    assert result.model_dump() == {"outcome": "revoked", "revoked_at": REVOKED_AT}


def test_verify_is_valid_again_after_the_student_is_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_store(monkeypatch, _archived())
    assert client.post("/verify", json={"code": LATEST_CODE}).json()["outcome"] == "revoked"
    _use_store(monkeypatch, tuple(v for v in DEMO_VERSIONS if v.email == STUDENT))
    assert client.post("/verify", json={"code": LATEST_CODE}).json()["outcome"] == "valid"


def test_unknown_code_is_still_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_store(monkeypatch, _archived())
    response = client.post("/verify", json={"code": "ZZZZ-ZZZZ-ZZZZ-ZZZZ"})
    assert response.json() == {"outcome": "not_found"}


# --- /me ---------------------------------------------------------------------------------


def test_archived_student_gets_a_clear_403_on_every_me_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_store(monkeypatch, _archived())
    headers = _headers()
    responses = [
        client.get("/me/passport", headers=headers),
        client.get("/me/passport/versions/2/pdf?lang=en", headers=headers),
        client.get("/me/passport/versions/1/pdf?lang=ka", headers=headers),
        client.get("/me/flags", headers=headers),
        client.post("/me/flags/seen", headers=headers),
        client.post(
            "/flags",
            headers=headers,
            json={"version": 2, "comment": "Something is wrong with this one."},
        ),
    ]
    for response in responses:
        assert response.status_code == 403
        assert response.json() == {"code": "passport_revoked"}
        assert "Nino" not in response.text


def test_archived_student_gets_no_pdf_even_with_files_in_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    path = "BTU-A1B2C3D4E5/v2/en.pdf"
    LocalPdfStorage(tmp_path).put(path, b"%PDF-1.4\nsecret")
    versions = tuple(replace(v, pdf_en_path=path, pdf_ka_path=path) for v in _archived())
    _use_store(monkeypatch, versions)
    response = client.get("/me/passport/versions/2/pdf?lang=en", headers=_headers())
    assert response.status_code == 403
    assert b"secret" not in response.content


def test_other_students_are_not_affected_by_an_archived_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    others = tuple(v for v in DEMO_VERSIONS if v.email != STUDENT)
    _use_store(monkeypatch, _archived() + others)
    response = client.get("/me/passport", headers=_headers("error.student@btu.edu.ge"))
    assert response.status_code == 200
    assert response.json()["passport"]["passport_id"] == "BTU-V2W3X4Y5Z6"


def test_restored_student_can_open_the_passport_again(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_store(monkeypatch, _archived())
    assert client.get("/me/passport", headers=_headers()).status_code == 403
    _use_store(monkeypatch, tuple(v for v in DEMO_VERSIONS if v.email == STUDENT))
    response = client.get("/me/passport", headers=_headers())
    assert response.status_code == 200
    assert response.json()["passport"]["passport_id"] == "BTU-A1B2C3D4E5"


def test_me_passport_marks_a_revoked_version_and_only_that_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_store(monkeypatch, _one_version_revoked())
    versions = client.get("/me/passport", headers=_headers()).json()["passport"]["versions"]
    by_number = {v["version"]: v for v in versions}
    assert by_number[1]["revoked_at"] == REVOKED_AT
    assert by_number[2]["revoked_at"] is None


def test_revoked_version_pdf_is_refused_but_the_good_one_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    storage = LocalPdfStorage(tmp_path)
    storage.put("p/v1.pdf", b"%PDF-1.4\nold")
    storage.put("p/v2.pdf", b"%PDF-1.4\nnew")
    versions = tuple(
        replace(v, pdf_en_path=f"p/v{v.version}.pdf", pdf_ka_path=f"p/v{v.version}.pdf")
        for v in _one_version_revoked()
    )
    _use_store(monkeypatch, versions)
    refused = client.get("/me/passport/versions/1/pdf?lang=en", headers=_headers())
    allowed = client.get("/me/passport/versions/2/pdf?lang=en", headers=_headers())
    assert refused.status_code == 403
    assert refused.json() == {"code": "version_revoked"}
    assert allowed.status_code == 200
    assert allowed.content == b"%PDF-1.4\nnew"


# --- SupabaseStore reads the new columns ---------------------------------------------------


def _row(*, revoked_at: str | None, deleted_at: str | None) -> dict[str, Any]:
    return {
        "student_id": "s1",
        "version_number": 1,
        "holder_name": "Nino Beridze",
        "verification_code": LATEST_CODE,
        "anchor_status": "confirmed",
        "tx_hash": "0x" + "11" * 32,
        "issued_at": "2026-01-01T00:00:00+00:00",
        "pdf_en_path": None,
        "pdf_ka_path": None,
        "revoked_at": revoked_at,
        "skill_entries": [],
        "students": {
            "email": STUDENT,
            "full_name": "Nino Beridze",
            "passport_id": "BTU-A1B2C3D4E5",
            "deleted_at": deleted_at,
        },
    }


def test_supabase_find_reads_revocation_and_archive_dates() -> None:
    with patch("passport_api.supabase_store.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value
        execute = query.eq.return_value.limit.return_value.execute
        execute.return_value.data = [_row(revoked_at=REVOKED_AT, deleted_at=ARCHIVED_AT)]
        found = SupabaseStore().find(LATEST_CODE)
        selected = db.return_value.table.return_value.select.call_args.args[0]
    assert found is not None
    assert found.version_revoked_at == REVOKED_AT
    assert found.student_archived_at == ARCHIVED_AT
    assert found.revoked_at == REVOKED_AT
    assert "revoked_at" in selected
    assert "deleted_at" in selected


def test_supabase_find_returns_a_clean_version_when_nothing_is_set() -> None:
    with patch("passport_api.supabase_store.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value
        query.eq.return_value.limit.return_value.execute.return_value.data = [
            _row(revoked_at=None, deleted_at=None)
        ]
        found = SupabaseStore().find(LATEST_CODE)
    assert found is not None
    assert found.revoked_at is None


def test_supabase_versions_for_email_carries_the_archive_date_to_each_version() -> None:
    nested = {k: v for k, v in _row(revoked_at=None, deleted_at=None).items() if k != "students"}
    with patch("passport_api.supabase_store.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value
        query.eq.return_value.limit.return_value.execute.return_value.data = [
            {
                "email": STUDENT,
                "full_name": "Nino Beridze",
                "passport_id": "BTU-A1B2C3D4E5",
                "deleted_at": ARCHIVED_AT,
                "passport_versions": [nested],
            }
        ]
        versions = SupabaseStore().versions_for_email(STUDENT)
        selected = db.return_value.table.return_value.select.call_args.args[0]
    assert [v.student_archived_at for v in versions] == [ARCHIVED_AT]
    assert "revoked_at" in selected


# --- admin endpoints -----------------------------------------------------------------------


class _Query:
    def __init__(self, db: "_Db", name: str) -> None:
        self.db = db
        self.name = name
        self.filters: dict[str, Any] = {}
        self.change: dict[str, Any] | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_Query":
        return self

    def update(self, values: dict[str, Any]) -> "_Query":
        self.change = values
        return self

    def eq(self, column: str, value: Any) -> "_Query":
        self.filters[column] = value
        return self

    def limit(self, _count: int) -> "_Query":
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "_Query":
        return self

    def execute(self) -> Any:
        rows = [
            row
            for row in self.db.tables[self.name]
            if all(row.get(k) == v for k, v in self.filters.items())
        ]
        if self.change is not None:
            for row in rows:
                row.update(self.change)
        return type("Response", (), {"data": [dict(row) for row in rows]})()


class _Db:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "students": [
                {
                    "id": "aaaaaaaa-0000-0000-0000-000000000001",
                    "email": STUDENT,
                    "full_name": "Nino Beridze",
                    "passport_id": "BTU-A1B2C3D4E5",
                    "admin_managed": False,
                    "deleted_at": None,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "passport_versions": [
                {"id": "bbbbbbbb-0001-0000-0000-000000000001", "revoked_at": None},
            ],
        }

    def table(self, name: str) -> _Query:
        return _Query(self, name)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> _Db:
    fake = _Db()
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    monkeypatch.setattr(admin_mod, "get_supabase", lambda: fake)
    return fake


ADMIN = {"Authorization": "Bearer fake"}
PID = "BTU-A1B2C3D4E5"
VID = "bbbbbbbb-0001-0000-0000-000000000001"


def test_archive_then_restore_round_trip(db: _Db) -> None:
    student = db.tables["students"][0]
    assert client.delete(f"/admin/students/{PID}", headers=ADMIN).status_code == 204
    assert student["deleted_at"] is not None
    again = client.delete(f"/admin/students/{PID}", headers=ADMIN)
    assert again.json() == {"code": "student_already_deleted"}
    assert client.post(f"/admin/students/{PID}/restore", headers=ADMIN).status_code == 204
    assert student["deleted_at"] is None


def test_restore_of_an_active_student_is_a_409(db: _Db) -> None:
    response = client.post(f"/admin/students/{PID}/restore", headers=ADMIN)
    assert response.status_code == 409
    assert response.json() == {"code": "student_not_deleted"}


def test_restore_unknown_student_is_a_404(db: _Db) -> None:
    response = client.post("/admin/students/BTU-NOBODY0000/restore", headers=ADMIN)
    assert response.status_code == 404
    assert response.json() == {"code": "student_not_found"}


def test_revoke_and_unrevoke_a_version(db: _Db) -> None:
    version = db.tables["passport_versions"][0]
    assert client.post(f"/admin/versions/{VID}/revoke", headers=ADMIN).status_code == 204
    assert version["revoked_at"] is not None
    again = client.post(f"/admin/versions/{VID}/revoke", headers=ADMIN)
    assert (again.status_code, again.json()) == (409, {"code": "version_already_revoked"})
    assert client.post(f"/admin/versions/{VID}/unrevoke", headers=ADMIN).status_code == 204
    assert version["revoked_at"] is None
    twice = client.post(f"/admin/versions/{VID}/unrevoke", headers=ADMIN)
    assert (twice.status_code, twice.json()) == (409, {"code": "version_not_revoked"})


def test_revoke_unknown_version_is_a_404(db: _Db) -> None:
    for action in ("revoke", "unrevoke"):
        response = client.post(f"/admin/versions/nope/{action}", headers=ADMIN)
        assert (response.status_code, response.json()) == (404, {"code": "version_not_found"})


def test_new_admin_routes_need_an_admin() -> None:
    for path in (
        f"/admin/students/{PID}/restore",
        f"/admin/versions/{VID}/revoke",
        f"/admin/versions/{VID}/unrevoke",
    ):
        assert client.post(path).status_code == 401


def test_admin_detail_still_shows_an_archived_student_with_revoked_dates(db: _Db) -> None:
    db.tables["students"][0]["deleted_at"] = ARCHIVED_AT
    version = {
        "id": VID,
        "version_number": 1,
        "holder_name": "Nino Beridze",
        "verification_code": LATEST_CODE,
        "anchor_status": "confirmed",
        "tx_hash": None,
        "issued_at": "2026-01-01T00:00:00+00:00",
        "pdf_en_path": None,
        "pdf_ka_path": None,
        "revoked_at": REVOKED_AT,
        "skill_entries": [],
        "student_id": "aaaaaaaa-0000-0000-0000-000000000001",
    }
    db.tables["passport_versions"] = [version]
    response = client.get(f"/admin/students/{PID}", headers=ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert body["deleted_at"].startswith("2026-10-30T10:00:00")
    assert body["versions"][0]["revoked_at"].startswith("2026-10-29T08:30:00")
