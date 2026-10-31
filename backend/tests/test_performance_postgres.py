"""Migration 0012 against a real Postgres: sync_student_units (many units in one call, each
in its own savepoint), admin_dashboard_stats and admin_health_snapshot."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from pg_support import MIGRATIONS, Database, PgClient, PgSyncStore, start_database
from postgrest.exceptions import APIError
from test_sync_postgres import ADA, BOB, _counts, _unit

import passport_api.sync as sync_mod
from passport_api.consistency import find_inconsistencies
from passport_api.schemas import Skill
from passport_api.sync import FakeSheet, StudentUnit, UnitResult, run_sync


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Database]:
    yield from start_database(tmp_path_factory)


@pytest.fixture(autouse=True)
def db(database: Database, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    database.reset()
    database.run("truncate sync_runs, flags")
    monkeypatch.setattr("passport_api.settings.settings.pdf_storage_dir", str(tmp_path))
    with patch("passport_api.sync.get_supabase", return_value=PgClient(database)):
        yield database


def _other(n: int) -> StudentUnit:
    return _unit(
        email=f"s{n}@btu.edu.ge",
        passport_id=f"BTU-{n:010d}",
        code=f"AAAA-BBBB-CCCC-{n:04d}",
        name=f"Student {n}",
        source_keys=(f"key-{n}",),
    )


def _anchor(db: Database, email: str, status: str) -> None:
    db.run(
        f"update passport_versions set anchor_status = '{status}' "
        f"where student_id = (select id from students where email = '{email}')"
    )


def _ok(outcome: UnitResult | Exception) -> UnitResult:
    assert not isinstance(outcome, Exception), outcome
    return outcome


# --- sync_student_units ---------------------------------------------------------------------


def test_many_units_are_stored_in_one_call(db: Database) -> None:
    store = PgSyncStore()
    outcomes = store.commit_student_units([_other(n) for n in range(1, 31)])
    assert len(outcomes) == 30
    assert all(_ok(o).created_version for o in outcomes)
    assert _counts(db) == (30, 30, 30, 30)
    assert find_inconsistencies(db.students_nested()) == []
    assert db.run("select * from sync_inconsistencies()") == ""


def test_a_failing_unit_is_reported_by_name_and_leaves_the_others_untouched(db: Database) -> None:
    store = PgSyncStore()
    later = (Skill(skill="Rust", badge="", awarded_on=None),)
    store.commit_student_units([_other(1)])
    # Unit 1 is stale (it expects no version, but one exists), unit 2 is new.
    stale = _unit(
        email="s1@btu.edu.ge",
        passport_id="BTU-0000000001",
        code="AAAA-BBBB-CCCC-9999",
        name="Student 1",
        number=2,
        expected=0,
        skills=later,
        source_keys=("key-1b",),
    )
    outcomes = store.commit_student_units([stale, _other(2)])
    assert isinstance(outcomes[0], APIError)
    assert outcomes[0].code == "PS001"
    assert _ok(outcomes[1]).created_student
    # Nothing of the stale unit survived: still one version for student 1.
    one = "select id from students where email = 's1@btu.edu.ge'"
    assert db.run(f"select count(*) from passport_versions where student_id = ({one})") == "1"
    assert _counts(db) == (2, 2, 2, 2)
    assert find_inconsistencies(db.students_nested()) == []


def test_a_half_written_unit_is_undone_without_touching_earlier_units_in_the_batch(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = sync_mod._unit_payload

    def payload(unit: StudentUnit) -> dict[str, Any]:
        body = real(unit)
        if unit.email == "s2@btu.edu.ge":
            body["source_keys"] = [None]  # fails after the student and version are written
        return body

    monkeypatch.setattr(sync_mod, "_unit_payload", payload)
    outcomes = PgSyncStore().commit_student_units([_other(1), _other(2), _other(3)])
    assert [isinstance(o, Exception) for o in outcomes] == [False, True, False]
    assert db.run("select string_agg(email, ',' order by email) from students") == (
        "s1@btu.edu.ge,s3@btu.edu.ge"
    )
    assert _counts(db) == (2, 2, 2, 2)
    assert find_inconsistencies(db.students_nested()) == []


def test_a_batch_equals_the_same_units_committed_one_by_one(db: Database) -> None:
    store = PgSyncStore()
    store.commit_student_units([_other(n) for n in range(1, 6)])
    batched = db.run(
        "select md5(string_agg(t::text, '' order by t.email)) from "
        "(select email, full_name, passport_id from students) t"
    )
    db.reset()
    for n in range(1, 6):
        store.commit_student_unit(_other(n))
    single = db.run(
        "select md5(string_agg(t::text, '' order by t.email)) from "
        "(select email, full_name, passport_id from students) t"
    )
    assert batched == single


def test_the_units_function_refuses_anything_but_an_array(db: Database) -> None:
    with pytest.raises(APIError) as caught:
        db.run("select sync_student_units('{}'::jsonb)")
    assert caught.value.code == "PS003"
    assert db.run("select sync_student_units('[]'::jsonb)") == "[]"


def test_a_full_sync_through_the_batch_function_matches_the_sheet(db: Database) -> None:
    rows = [ADA, BOB, {**BOB, "skill": "SQL", "awarded_on": ""}]
    sheet = FakeSheet(rows)
    result = run_sync(PgSyncStore(), sheet)
    assert result.status == "completed"
    assert _counts(db) == (2, 2, 3, 3)
    # An unchanged second run commits nothing new and writes the same statuses.
    again = FakeSheet(rows)
    result = run_sync(PgSyncStore(), again)
    assert result.versions_created == 0
    assert _counts(db) == (2, 2, 3, 3)
    assert [o.status for o in again.writes[0]] == ["SYNCED"] * 3


# --- admin_dashboard_stats ------------------------------------------------------------------


def test_the_dashboard_stats_count_what_the_dashboard_used_to_count(db: Database) -> None:
    PgSyncStore().commit_student_units([_other(n) for n in range(1, 5)])
    _anchor(db, "s1@btu.edu.ge", "confirmed")
    _anchor(db, "s2@btu.edu.ge", "retrying")
    _anchor(db, "s3@btu.edu.ge", "failed_permanent")
    db.run(
        """
        update students set deleted_at = now() where email = 's4@btu.edu.ge';
        update students set admin_managed = true where email = 's1@btu.edu.ge';
        insert into sync_runs (status, started_at)
            select 'completed', now() - (n || ' min')::interval
            from generate_series(1, 7) n;
        """
    )
    db.run(
        "insert into flags (passport_id, version, verification_code, student_email, comment, "
        "status) values "
        "('BTU-0000000002', 1, 'AAAA-BBBB-CCCC-0002', 's2@btu.edu.ge', 'something is wrong here', "
        "'open'), "
        "('BTU-0000000003', 1, 'AAAA-BBBB-CCCC-0003', 's3@btu.edu.ge', 'something is wrong too', "
        "'resolved')"
    )
    stats = db.json("select admin_dashboard_stats()")
    assert stats["total_students"] == 3  # the archived one is not counted
    assert stats["admin_managed_students"] == 1
    assert stats["pending_anchors"] == 3  # everything not confirmed, archived student included
    assert stats["failed_anchors"] == 1
    assert stats["open_flags"] == 1
    runs = stats["recent_runs"]
    assert len(runs) == 5
    assert [r["started_at"] for r in runs] == sorted((r["started_at"] for r in runs), reverse=True)
    assert set(runs[0]) == {
        "id",
        "status",
        "started_at",
        "finished_at",
        "rows_read",
        "versions_created",
        "error",
    }


def test_the_dashboard_stats_work_on_an_empty_database(db: Database) -> None:
    assert db.json("select admin_dashboard_stats()") == {
        "total_students": 0,
        "admin_managed_students": 0,
        "pending_anchors": 0,
        "failed_anchors": 0,
        "open_flags": 0,
        "recent_runs": [],
    }


# --- admin_health_snapshot ------------------------------------------------------------------


def test_the_health_snapshot_has_what_the_banner_reads(db: Database) -> None:
    PgSyncStore().commit_student_units([_other(1), _other(2)])
    _anchor(db, "s1@btu.edu.ge", "confirmed")
    db.run(
        """
        insert into sync_runs (status, started_at, finished_at) values
            ('completed', now() - interval '3 hours', now() - interval '3 hours'),
            ('failed', now() - interval '1 hour', now() - interval '1 hour'),
            ('running', now(), null);
        """
    )
    snap = db.json("select admin_health_snapshot()")
    assert snap["last_finished_run"]["status"] == "failed"
    assert snap["last_success_run"]["status"] == "completed"
    assert [v["anchor_status"] for v in snap["open_versions"]] == ["pending"]
    assert snap["inconsistencies"] == 0


def test_the_health_snapshot_counts_half_written_rows(db: Database) -> None:
    PgSyncStore().commit_student_units([_other(1)])
    db.run("delete from skill_entries")
    assert db.json("select admin_health_snapshot()")["inconsistencies"] >= 1


def test_the_health_snapshot_is_empty_but_valid_on_a_new_database(db: Database) -> None:
    assert db.json("select admin_health_snapshot()") == {
        "last_finished_run": None,
        "last_success_run": None,
        "open_versions": [],
        "inconsistencies": 0,
    }


# --- the migration itself -------------------------------------------------------------------


def test_the_migration_runs_twice_and_only_the_service_role_can_call_it(db: Database) -> None:
    sql = (MIGRATIONS / "0012_performance.sql").read_text(encoding="utf-8")
    db.run(sql)
    db.run(sql)
    for function in (
        "sync_student_units(jsonb)",
        "admin_dashboard_stats()",
        "admin_health_snapshot()",
    ):
        allowed = {
            role: db.run(f"select has_function_privilege('{role}', '{function}', 'execute')")
            for role in ("anon", "authenticated", "service_role")
        }
        assert allowed == {"anon": "f", "authenticated": "f", "service_role": "t"}
    indexes = db.run(
        "select string_agg(indexname, ',' order by indexname) from pg_indexes "
        "where tablename = 'sync_runs' and indexname like 'sync_runs_%idx'"
    )
    assert indexes == "sync_runs_started_at_idx,sync_runs_status_started_idx"
