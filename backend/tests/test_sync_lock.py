"""A sync killed mid-run must not block every later sync."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from passport_api.sync import (
    STALE_LOCK_AFTER,
    FakeSheet,
    MemorySyncStore,
    SupabaseSyncStore,
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


def test_existing_email_conflict_fails_that_row_and_the_run_continues() -> None:
    from passport_api.sync import StudentRecord

    store = MemorySyncStore()
    # A student row exists without versions (the shape of the old admin-managed rows).
    store.students.append(StudentRecord("clash@btu.edu.ge", "Clash", "BTU-CLASH00001"))
    sheet = FakeSheet([_row("clash@btu.edu.ge", "Clash"), _row("fine@btu.edu.ge", "Fine")])
    result = run_sync(store, sheet)
    assert result.status == "completed"
    assert result.versions_created == 1
    outcomes = {o.index: o for o in sheet.writes[0]}
    assert (outcomes[0].status, outcomes[0].error) == ("FAILED", "student_conflict")
    assert outcomes[1].status == "SYNCED"
    assert [s.email for s in store.students] == ["clash@btu.edu.ge", "fine@btu.edu.ge"]
    assert store.runs[-1].status == "completed"


def test_unexpected_error_marks_only_that_student(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemorySyncStore()
    original = store.insert_student

    def flaky(email: str, full_name: str, passport_id: str) -> None:
        if email == "bad@btu.edu.ge":
            raise RuntimeError("secret internal detail")
        original(email, full_name, passport_id)

    monkeypatch.setattr(store, "insert_student", flaky)
    sheet = FakeSheet([_row("bad@btu.edu.ge", "Bad"), _row("good@btu.edu.ge", "Good")])
    result = run_sync(store, sheet)
    assert result.status == "completed"
    assert result.versions_created == 1
    outcomes = {o.index: o for o in sheet.writes[0]}
    assert (outcomes[0].status, outcomes[0].error) == ("FAILED", "sync_error")
    assert outcomes[1].status == "SYNCED"


def test_supabase_student_lookup_includes_admin_managed_students() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value
        query.is_.return_value.execute.return_value.data = [
            {
                "email": "luka@btu.edu.ge",
                "full_name": "Luka",
                "passport_id": "BTU-J63ZVDGDK4",
                "passport_versions": [
                    {"version_number": 1, "skill_fingerprint": "f", "holder_name": "Luka"}
                ],
            }
        ]
        states = SupabaseSyncStore().current_students()
        assert list(states) == ["luka@btu.edu.ge"]
        # Only archived students are left out. admin_managed is not a filter any more.
        query.eq.assert_not_called()
        query.is_.assert_called_once_with("deleted_at", "null")
