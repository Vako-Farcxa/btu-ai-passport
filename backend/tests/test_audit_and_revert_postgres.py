"""Migration 0013 against a real Postgres: a skill set can come back after a change, and the
admin_audit table accepts valid rows, refuses bad ones and hides every row from anon."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from pg_support import Database, PgClient, PgSyncStore, start_database
from postgrest.exceptions import APIError
from test_sync_postgres import ADA

from passport_api.consistency import find_inconsistencies
from passport_api.sync import FakeSheet, run_sync


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Database]:
    yield from start_database(tmp_path_factory)


@pytest.fixture(autouse=True)
def db(database: Database, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    database.reset()
    database.run("truncate admin_audit")
    monkeypatch.setattr("passport_api.settings.settings.pdf_storage_dir", str(tmp_path))
    with patch("passport_api.sync.get_supabase", return_value=PgClient(database)):
        yield database


def _sync(rows: list[dict[str, str]]) -> FakeSheet:
    sheet = FakeSheet(rows)
    assert run_sync(PgSyncStore(), sheet).status == "completed"
    return sheet


RUST = {**ADA, "skill": "Rust", "awarded_on": "2025-02-01"}


# -- a skill set may come back ---------------------------------------------------------


def test_the_old_one_version_per_skill_set_rule_is_gone(db: Database) -> None:
    assert (
        db.run(
            "select count(*) from pg_constraint where conname = 'passport_versions_student_skill'"
        )
        == "0"
    )


def test_returning_to_an_earlier_skill_set_makes_a_new_version_instead_of_failing(
    db: Database,
) -> None:
    _sync([ADA])
    _sync([ADA, RUST])
    sheet = _sync([ADA])  # the Rust award was taken back
    assert [(o.status, o.version, o.error) for o in sheet.writes[0]] == [("SYNCED", "V3", "")]
    assert (
        db.run(
            "select string_agg(version_number::text, ',' order by version_number) "
            "from passport_versions"
        )
        == "1,2,3"
    )
    # Version 3 holds the same skills as version 1, under its own code and its own hash.
    assert db.run("select count(distinct skill_fingerprint) from passport_versions") == "2"
    assert db.run("select count(distinct verification_code) from passport_versions") == "3"
    assert db.run("select count(distinct content_hash) from passport_versions") == "3"
    assert find_inconsistencies(db.students_nested()) == []


def test_going_back_and_forth_keeps_working_and_a_quiet_run_adds_nothing(db: Database) -> None:
    for rows in ([ADA], [ADA, RUST], [ADA], [ADA, RUST], [ADA, RUST]):
        _sync(rows)
    assert db.count("passport_versions") == 4


def test_two_versions_of_one_student_still_cannot_share_a_number(db: Database) -> None:
    _sync([ADA])
    with pytest.raises(APIError) as caught:
        db.run(
            "insert into passport_versions (student_id, version_number, holder_name, "
            "verification_code, verification_id_hash, skill_fingerprint, content_hash) "
            "select student_id, version_number, holder_name, 'ZZZZ-ZZZZ-ZZZZ-ZZZZ', "
            "'0x' || repeat('a', 64), '0x' || repeat('b', 64), '0x' || repeat('c', 64) "
            "from passport_versions"
        )
    assert caught.value.code == "23505"


# -- the audit table -------------------------------------------------------------------


def test_an_audit_row_gets_defaults_and_keeps_its_detail(db: Database) -> None:
    db.run(
        "insert into admin_audit (actor, action, target_type, target, detail) values "
        "('a@btu.edu.ge', 'student.archive', 'student', 'BTU-1', '{\"n\": 2}')"
    )
    row = db.json("select row_to_json(t) from (select * from admin_audit) t")
    assert row["actor"] == "a@btu.edu.ge"
    assert row["detail"] == {"n": 2}
    assert row["id"] and row["created_at"]


@pytest.mark.parametrize(
    "values",
    [
        "('a@btu.edu.ge', '')",
        "('a@btu.edu.ge', repeat('x', 65))",
        "(null, 'x.y')",
    ],
)
def test_a_bad_audit_row_is_refused(db: Database, values: str) -> None:
    with pytest.raises(APIError):
        db.run(f"insert into admin_audit (actor, action) values {values}")
    assert db.count("admin_audit") == 0


def test_an_over_long_target_is_refused(db: Database) -> None:
    with pytest.raises(APIError):
        db.run(
            "insert into admin_audit (actor, action, target) values ('a', 'x.y', repeat('t', 201))"
        )


def test_the_audit_table_has_row_level_security_and_no_policy_so_anon_sees_nothing(
    db: Database,
) -> None:
    db.run("insert into admin_audit (actor, action) values ('a@btu.edu.ge', 'x.y')")
    assert db.run("select relrowsecurity from pg_class where relname = 'admin_audit'") == "t"
    assert db.run("select count(*) from pg_policies where tablename = 'admin_audit'") == "0"
    # Give anon the table privilege, as Supabase does by default: RLS alone must hide the row.
    db.run("grant select on admin_audit to anon")
    try:
        assert db.run("set role anon; select count(*) from admin_audit;").splitlines()[-1] == "0"
    finally:
        db.run("revoke select on admin_audit from anon")


def test_the_newest_audit_rows_come_first_by_index_order(db: Database) -> None:
    for number in range(3):
        db.run(
            f"insert into admin_audit (actor, action, target, created_at) values "
            f"('a', 'x.y', '{number}', now() + interval '{number} minute')"
        )
    assert (
        db.run(
            "select string_agg(target, ',') from (select target from admin_audit "
            "order by created_at desc limit 2) t"
        )
        == "2,1"
    )
