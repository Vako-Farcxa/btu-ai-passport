"""A sync killed mid-run must not block every later sync."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from passport_api.sync import (
    STALE_LOCK_AFTER,
    FakeSheet,
    MemorySyncStore,
    StudentUnit,
    SupabaseSyncStore,
    UnitResult,
    run_sync,
)

ROW = {
    "email": "ada@btu.edu.ge",
    "full_name": "Ada Lovelace",
    "skill": "Python",
    "badge": "Foundation",
    "awarded_on": "2025-01-15",
}


def stuck_store(age: timedelta) -> MemorySyncStore:
    store = MemorySyncStore()
    assert store.try_acquire()
    store.runs[0].started_at = datetime.now(UTC) - age
    return store


def test_stale_running_row_is_released_and_the_sync_runs() -> None:
    store = stuck_store(STALE_LOCK_AFTER + timedelta(minutes=1))
    result = run_sync(store, FakeSheet([ROW]))
    assert result.status == "completed"
    assert result.versions_created == 1
    assert (store.runs[0].status, store.runs[0].error) == ("failed", "stale_lock")
    assert store.runs[1].status == "completed"


def test_fresh_running_row_still_skips() -> None:
    store = stuck_store(timedelta(minutes=9))
    result = run_sync(store, FakeSheet([ROW]))
    assert result.status == "skipped"
    assert store.runs[0].status == "running"
    assert store.runs[1].status == "skipped"
    assert store.versions == []


def test_failed_finish_releases_the_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemorySyncStore()

    def broken_finish(rows_read: int, versions_created: int) -> None:
        raise RuntimeError("database_down")

    monkeypatch.setattr(store, "finish", broken_finish)
    with pytest.raises(RuntimeError, match="database_down"):
        run_sync(store, FakeSheet([ROW]))
    assert (store.runs[0].status, store.runs[0].error) == ("failed", "sync_finish_failed")
    monkeypatch.undo()
    assert run_sync(store, FakeSheet([ROW])).status == "completed"


def test_failure_while_issuing_marks_the_run_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemorySyncStore()

    def broken(*_args: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "upsert_skills", broken)
    with pytest.raises(RuntimeError, match="boom"):
        run_sync(store, FakeSheet([ROW]))
    assert (store.runs[0].status, store.runs[0].error) == ("failed", "sync_failed")


def test_supabase_store_releases_runs_older_than_the_limit() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        table = db.return_value.table.return_value
        table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        table.insert.return_value.execute.return_value.data = [{"id": "run-1"}]
        before = datetime.now(UTC)
        assert SupabaseSyncStore().try_acquire() is True
        update = table.update
        values = update.call_args.args[0]
        assert values["status"] == "failed"
        assert values["error"] == "stale_lock"
        update.return_value.eq.assert_called_once_with("status", "running")
        cutoff = datetime.fromisoformat(update.return_value.eq.return_value.lt.call_args.args[1])
        assert update.return_value.eq.return_value.lt.call_args.args[0] == "started_at"
        assert before - STALE_LOCK_AFTER - timedelta(seconds=5) <= cutoff
        assert cutoff <= datetime.now(UTC) - STALE_LOCK_AFTER + timedelta(seconds=5)
        update.return_value.eq.return_value.lt.return_value.execute.assert_called_once()


def test_supabase_store_still_skips_while_a_fresh_run_is_running() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        table = db.return_value.table.return_value
        running = table.select.return_value.eq.return_value.limit.return_value.execute
        running.return_value.data = [{"id": "run-1"}]
        assert SupabaseSyncStore().try_acquire() is False
        table.insert.assert_not_called()


# ---------------------------------------------------------------------------
# One student must not stop the run
# ---------------------------------------------------------------------------


def _row(email: str, name: str) -> dict[str, str]:
    return {**ROW, "email": email, "full_name": name}


def test_student_without_a_version_is_healed_by_the_next_sync() -> None:
    from passport_api.sync import StudentRecord

    store = MemorySyncStore()
    # A student row exists without versions (old admin-managed rows, or a crashed old sync).
    store.students.append(StudentRecord("clash@btu.edu.ge", "Clash", "BTU-CLASH00001"))
    sheet = FakeSheet([_row("clash@btu.edu.ge", "Clash"), _row("fine@btu.edu.ge", "Fine")])
    result = run_sync(store, sheet)
    assert result.status == "completed"
    assert result.versions_created == 2
    outcomes = {o.index: o for o in sheet.writes[0]}
    assert (outcomes[0].status, outcomes[0].version) == ("SYNCED", "V1")
    assert outcomes[0].passport_id == "BTU-CLASH00001"
    assert outcomes[1].status == "SYNCED"
    assert [s.email for s in store.students] == ["clash@btu.edu.ge", "fine@btu.edu.ge"]
    assert {v.email: v.passport_id for v in store.versions}["clash@btu.edu.ge"] == "BTU-CLASH00001"
    assert store.runs[-1].status == "completed"


def test_a_unique_violation_from_the_database_fails_that_row_and_the_run_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from postgrest.exceptions import APIError

    store = MemorySyncStore()
    original = store.commit_student_unit

    def clashing(unit: StudentUnit) -> UnitResult:
        if unit.email == "clash@btu.edu.ge":
            raise APIError({"code": "23505", "message": "students_email_key"})
        return original(unit)

    monkeypatch.setattr(store, "commit_student_unit", clashing)
    sheet = FakeSheet([_row("clash@btu.edu.ge", "Clash"), _row("fine@btu.edu.ge", "Fine")])
    result = run_sync(store, sheet)
    assert result.versions_created == 1
    outcomes = {o.index: o for o in sheet.writes[0]}
    assert (outcomes[0].status, outcomes[0].error) == ("FAILED", "student_conflict")
    assert outcomes[1].status == "SYNCED"
    assert [s.email for s in store.students] == ["fine@btu.edu.ge"]


def test_unexpected_error_marks_only_that_student(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemorySyncStore()
    original = store.commit_student_unit

    def flaky(unit: StudentUnit) -> UnitResult:
        if unit.email == "bad@btu.edu.ge":
            raise RuntimeError("secret internal detail")
        return original(unit)

    monkeypatch.setattr(store, "commit_student_unit", flaky)
    sheet = FakeSheet([_row("bad@btu.edu.ge", "Bad"), _row("good@btu.edu.ge", "Good")])
    result = run_sync(store, sheet)
    assert result.status == "completed"
    assert result.versions_created == 1
    outcomes = {o.index: o for o in sheet.writes[0]}
    assert (outcomes[0].status, outcomes[0].error) == ("FAILED", "sync_error")
    assert outcomes[1].status == "SYNCED"


def test_supabase_student_lookup_includes_admin_managed_students() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        select = db.return_value.table.return_value.select.return_value
        query = select.order.return_value.range.return_value
        query.execute.return_value.data = [
            {
                "email": "luka@btu.edu.ge",
                "full_name": "Luka",
                "passport_id": "BTU-J63ZVDGDK4",
                "deleted_at": None,
                "passport_versions": [
                    {"version_number": 1, "skill_fingerprint": "f", "holder_name": "Luka"}
                ],
            }
        ]
        states = SupabaseSyncStore().current_students()
        assert list(states) == ["luka@btu.edu.ge"]
        assert states["luka@btu.edu.ge"].archived is False
        # admin_managed is not a filter, and archived students are no longer filtered out
        # either: they are returned flagged, so the sync can refuse them by name.
        query.eq.assert_not_called()
        query.is_.assert_not_called()


def test_supabase_student_lookup_flags_archived_students() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        select = db.return_value.table.return_value.select.return_value
        query = select.order.return_value.range.return_value
        query.execute.return_value.data = [
            {
                "email": "gone@btu.edu.ge",
                "full_name": "Gone Student",
                "passport_id": "BTU-GONE000001",
                "deleted_at": "2026-10-30T10:00:00+00:00",
                "passport_versions": [
                    {"version_number": 2, "skill_fingerprint": "f", "holder_name": "Gone"}
                ],
            },
            {
                "email": "novers@btu.edu.ge",
                "full_name": "No Versions",
                "passport_id": "BTU-NOVERS0001",
                "deleted_at": "2026-10-30T10:00:00+00:00",
                "passport_versions": [],
            },
            {
                "email": "empty@btu.edu.ge",
                "full_name": "Active Without Versions",
                "passport_id": "BTU-EMPTY00001",
                "deleted_at": None,
                "passport_versions": [],
            },
        ]
        states = SupabaseSyncStore().current_students()
    assert states["gone@btu.edu.ge"].archived is True
    assert states["gone@btu.edu.ge"].latest_version == 2
    assert states["novers@btu.edu.ge"].archived is True
    assert states["novers@btu.edu.ge"].latest_version == 0
    # An active student with no version yet is listed (version 0) so the sync can heal it.
    assert states["empty@btu.edu.ge"].latest_version == 0
    assert states["empty@btu.edu.ge"].latest_fingerprint == ""
    assert states["empty@btu.edu.ge"].archived is False


def test_sync_refuses_new_versions_for_an_archived_student() -> None:
    store = MemorySyncStore()
    result = run_sync(store, FakeSheet([ROW]))
    assert result.status == "completed"
    assert len(store.versions) == 1
    store.students[0].archived = True
    changed = {**ROW, "skill": "Prompting"}
    sheet = FakeSheet([ROW, changed])
    result = run_sync(store, sheet)
    assert result.status == "completed"
    assert result.versions_created == 0
    assert len(store.versions) == 1
    outcomes = sheet.writes[0]
    assert {(o.status, o.error) for o in outcomes} == {("FAILED", "student_archived")}
    assert all(o.passport_id == store.students[0].passport_id for o in outcomes)


def test_restoring_an_archived_student_lets_the_sync_issue_versions_again() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([ROW]))
    store.students[0].archived = True
    changed = {**ROW, "skill": "Prompting"}
    run_sync(store, FakeSheet([ROW, changed]))
    assert len(store.versions) == 1
    store.students[0].archived = False
    result = run_sync(store, FakeSheet([ROW, changed]))
    assert result.versions_created == 1
    assert len(store.versions) == 2
