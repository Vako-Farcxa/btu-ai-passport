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
