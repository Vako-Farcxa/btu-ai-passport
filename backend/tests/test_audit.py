"""The admin audit log: every admin write leaves one row, a failed audit write never blocks the
change, and only an admin can read the log."""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_admin_skills import FakeAdminSheet, FakeDb, existing_row, seed_skill
from test_revocation import PID, VID, _Db

import passport_api.api.admin as admin_mod
import passport_api.audit as audit
from passport_api.api.admin import get_admin_sheet
from passport_api.api.sync import get_sync_store
from passport_api.audit import MemoryAuditStore, SupabaseAuditStore, record_admin_action
from passport_api.flags import MemoryFlagStore, get_flag_store
from passport_api.main import app
from passport_api.settings import settings
from passport_api.sync import MemorySyncStore

client = TestClient(app)
ADMIN = {"Authorization": "Bearer fake"}
ACTOR = "admin@btu.edu.ge"


@pytest.fixture(autouse=True)
def admin(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: ACTOR)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def revocation_db(monkeypatch: pytest.MonkeyPatch) -> _Db:
    fake = _Db()
    fake.tables["passport_versions"][0].update(
        {
            "version_number": 2,
            "students": {"passport_id": PID},
        }
    )
    monkeypatch.setattr(admin_mod, "get_supabase", lambda: fake)
    return fake


def rows() -> list[dict[str, Any]]:
    return [entry.model_dump(mode="json") for entry in reversed(audit.memory_store.entries)]


# -- what gets written ------------------------------------------------------------------


def test_archive_and_restore_a_student_are_recorded(revocation_db: _Db) -> None:
    assert client.delete(f"/admin/students/{PID}", headers=ADMIN).status_code == 204
    assert client.post(f"/admin/students/{PID}/restore", headers=ADMIN).status_code == 204
    newest, oldest = rows()
    assert (oldest["action"], oldest["actor"], oldest["target"]) == (
        "student.archive",
        ACTOR,
        PID,
    )
    assert (newest["action"], newest["target_type"]) == ("student.restore", "student")


def test_revoke_and_unrevoke_record_the_version_and_its_student(revocation_db: _Db) -> None:
    client.post(f"/admin/versions/{VID}/revoke", headers=ADMIN)
    client.post(f"/admin/versions/{VID}/unrevoke", headers=ADMIN)
    newest, oldest = rows()
    assert oldest["action"] == "version.revoke"
    assert oldest["target"] == VID
    assert oldest["detail"] == {"passport_id": PID, "version": 2}
    assert newest["action"] == "version.unrevoke"


def test_a_refused_action_writes_nothing(revocation_db: _Db) -> None:
    assert client.post(f"/admin/students/{PID}/restore", headers=ADMIN).status_code == 409
    assert client.post(f"/admin/versions/{VID}/unrevoke", headers=ADMIN).status_code == 409
    assert client.post("/admin/versions/nope/revoke", headers=ADMIN).status_code == 404
    assert rows() == []


def test_the_actor_is_the_signed_in_admin_not_something_the_caller_sends(
    revocation_db: _Db,
) -> None:
    client.delete(f"/admin/students/{PID}?actor=someone@else.ge", headers=ADMIN)
    assert [row["actor"] for row in rows()] == [ACTOR]


def test_skill_changes_and_awards_are_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    db, sheet, store = FakeDb(), FakeAdminSheet([existing_row()]), MemorySyncStore()
    monkeypatch.setattr(admin_mod, "get_supabase", lambda: db)
    app.dependency_overrides[get_admin_sheet] = lambda: sheet
    app.dependency_overrides[get_sync_store] = lambda: store
    created = client.post(
        "/admin/skills", headers=ADMIN, json={"name": "Data Ethics", "category": "AI Skill"}
    )
    skill_id = created.json()["id"]
    client.patch(f"/admin/skills/{skill_id}", headers=ADMIN, json={"name_ka": "ეთიკა"})
    seed_skill(db)
    client.post(
        "/admin/awards",
        headers=ADMIN,
        json={
            "skill_id": "SKL-002",
            "awarded_on": "2026-10-28",
            "students": [
                {"email": "nino@btu.edu.ge", "first_name": "Nino", "last_name": "Beridze"},
                {"email": "bad@gmail.com", "first_name": "Bad"},
            ],
        },
    )
    by_action = {row["action"]: row for row in rows()}
    assert by_action["skill.create"]["target"] == skill_id
    assert by_action["skill.update"]["detail"] == {"fields": "name_ka"}
    award = by_action["skill.award"]
    assert award["target"].startswith("BTU-")
    assert award["detail"]["skill_id"] == "SKL-002"
    assert award["detail"]["status"] == "synced"
    # The rejected student produced no row, and only one award row exists.
    assert [row["action"] for row in rows()].count("skill.award") == 1


def test_resolving_a_flag_is_recorded() -> None:
    flags = MemoryFlagStore()
    app.dependency_overrides[get_flag_store] = lambda: flags
    record = flags.create(
        passport_id=PID,
        version=1,
        verification_code="AAAA-BBBB-CCCC-DDDD",
        student_email="s@btu.edu.ge",
        comment="Something looks wrong here.",
    )
    client.patch(
        f"/admin/flags/{record.id}", headers=ADMIN, json={"status": "dismissed", "admin_note": ""}
    )
    (entry,) = rows()
    assert entry["action"] == "flag.dismissed"
    assert entry["target"] == record.id
    assert entry["detail"] == {"passport_id": PID, "version": 1}


# -- it never blocks the change --------------------------------------------------------


def test_a_failing_audit_write_does_not_undo_or_fail_the_change(
    revocation_db: _Db, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(**_kwargs: Any) -> None:
        raise RuntimeError("password=hunter2 row=secret")

    monkeypatch.setattr(audit.memory_store, "add", boom)
    with caplog.at_level(logging.ERROR, logger="passport_api.audit"):
        response = client.delete(f"/admin/students/{PID}", headers=ADMIN)
    assert response.status_code == 204
    assert revocation_db.tables["students"][0]["deleted_at"] is not None
    assert "audit_write_failed action=student.archive error=RuntimeError" in caplog.text
    assert "hunter2" not in caplog.text


def test_record_admin_action_cuts_an_over_long_target() -> None:
    record_admin_action(ACTOR, "x.y", target="t" * 500)
    assert len(audit.memory_store.entries[0].target) == 200


# -- reading it ------------------------------------------------------------------------


def test_the_log_lists_newest_first_and_honours_limit() -> None:
    for number in range(5):
        record_admin_action(ACTOR, "demo.step", target=str(number))
    body = client.get("/admin/audit?limit=3", headers=ADMIN).json()
    assert [entry["target"] for entry in body["entries"]] == ["4", "3", "2"]
    assert set(body["entries"][0]) == {
        "id",
        "created_at",
        "actor",
        "action",
        "target_type",
        "target",
        "detail",
    }


def test_the_log_limit_is_bounded() -> None:
    assert client.get("/admin/audit?limit=0", headers=ADMIN).status_code == 422
    assert client.get("/admin/audit?limit=501", headers=ADMIN).status_code == 422


def test_the_log_needs_an_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    assert client.get("/admin/audit").status_code == 401


def test_an_unreadable_log_is_a_503_with_the_standard_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Broken(MemoryAuditStore):
        def recent(self, limit: int) -> list[Any]:
            raise RuntimeError("relation does not exist")

    monkeypatch.setattr(admin_mod, "get_audit_store", lambda: Broken())
    response = client.get("/admin/audit", headers=ADMIN)
    assert (response.status_code, response.json()) == (503, {"code": "audit_unavailable"})


def test_memory_store_is_used_without_supabase_and_supabase_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert audit.get_audit_store() is audit.memory_store
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    assert isinstance(audit.get_audit_store(), SupabaseAuditStore)


# -- the Supabase store ----------------------------------------------------------------


class _Table:
    def __init__(self, data: Any = None) -> None:
        self.inserted: list[dict[str, Any]] = []
        self.calls: list[tuple[str, Any]] = []
        self._data = data

    def insert(self, row: dict[str, Any]) -> "_Table":
        self.inserted.append(row)
        return self

    def select(self, columns: str) -> "_Table":
        self.calls.append(("select", columns))
        return self

    def order(self, column: str, desc: bool = False) -> "_Table":
        self.calls.append(("order", (column, desc)))
        return self

    def limit(self, count: int) -> "_Table":
        self.calls.append(("limit", count))
        return self

    def execute(self) -> Any:
        return type("Response", (), {"data": self._data})()


def test_supabase_store_inserts_and_reads_the_audit_table(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _Table(
        [
            {
                "id": "1",
                "created_at": "2026-10-31T10:00:00+00:00",
                "actor": ACTOR,
                "action": "sync.run",
                "target_type": "sync",
                "target": "",
                "detail": {"rows_read": 3},
            },
            "garbage",
        ]
    )
    asked: list[str] = []

    class Client:
        def table(self, name: str) -> _Table:
            asked.append(name)
            return table

    monkeypatch.setattr(audit, "get_supabase", lambda: Client())
    store = SupabaseAuditStore()
    store.add(actor=ACTOR, action="sync.run", target_type="sync", target="", detail={"a": 1})
    assert table.inserted == [
        {
            "actor": ACTOR,
            "action": "sync.run",
            "target_type": "sync",
            "target": "",
            "detail": {"a": 1},
        }
    ]
    entries = store.recent(10)
    assert [entry.action for entry in entries] == ["sync.run"]
    assert ("order", ("created_at", True)) in table.calls
    assert ("limit", 10) in table.calls
    assert set(asked) == {"admin_audit"}


def test_a_run_of_the_sync_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    from passport_api.schemas import SyncResult

    monkeypatch.setattr(
        admin_mod,
        "run_sync",
        lambda _store, _sheet: SyncResult(
            status="completed", rows_read=7, versions_created=2, error=None
        ),
    )
    monkeypatch.setattr(admin_mod, "SupabaseSyncStore", lambda: object())
    monkeypatch.setattr(admin_mod, "GspreadSheet", lambda: object())
    assert client.post("/admin/sync", headers=ADMIN).status_code == 200
    (entry,) = rows()
    assert entry["action"] == "sync.run"
    assert entry["detail"] == {"status": "completed", "rows_read": 7, "versions_created": 2}


def test_the_audit_row_and_the_change_belong_together(revocation_db: _Db) -> None:
    client.delete(f"/admin/students/{PID}", headers=ADMIN)
    assert revocation_db.tables["students"][0]["deleted_at"] is not None
    assert rows()[0]["target"] == revocation_db.tables["students"][0]["passport_id"]
