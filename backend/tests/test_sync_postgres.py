"""The sync_student_unit function and the sync against a real Postgres: a crash in the middle
of a student's unit must leave nothing behind, retries must change nothing, and the stored
skills must hash to the stored hashes."""

import json
import threading
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from unittest.mock import patch

import pytest
from pg_support import Database, PgClient, PgSyncStore, start_database
from postgrest.exceptions import APIError

import passport_api.sync as sync_mod
from passport_api.anchoring import SNAPSHOT_MISMATCH
from passport_api.consistency import find_inconsistencies
from passport_api.fingerprint import content_hash, skill_fingerprint, verification_id_hash
from passport_api.schemas import Skill
from passport_api.sync import (
    SYNC_STALE,
    FakeSheet,
    StudentUnit,
    VersionRecord,
    run_sync,
)

ADA = {
    "email": "ada@btu.edu.ge",
    "full_name": "Ada Lovelace",
    "skill": "Python",
    "badge": "Foundation",
    "awarded_on": "2025-01-15",
}
BOB = {**ADA, "email": "bob@btu.edu.ge", "full_name": "Bob Stone"}
PASSPORT = "BTU-00000000AA"


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Database]:
    yield from start_database(tmp_path_factory)


@pytest.fixture(autouse=True)
def db(database: Database, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    database.reset()
    monkeypatch.setattr("passport_api.settings.settings.pdf_storage_dir", str(tmp_path))
    with patch("passport_api.sync.get_supabase", return_value=PgClient(database)):
        yield database


def _unit(
    *,
    email: str = ADA["email"],
    passport_id: str = PASSPORT,
    number: int = 1,
    expected: int = 0,
    skills: tuple[Skill, ...] | None = None,
    code: str = "ABCD-EFGH-JKMN-PQRS",
    source_keys: tuple[str, ...] = ("k1",),
    rename: bool = False,
    name: str = "Ada Lovelace",
) -> StudentUnit:
    stored = skills or (Skill(skill="Python", badge="Foundation", awarded_on="2025-01-15"),)
    version = VersionRecord(
        passport_id=passport_id,
        email=email,
        version_number=number,
        holder_name=name,
        verification_code=code,
        verification_id_hash=verification_id_hash(code),
        skill_fingerprint=skill_fingerprint(stored),
        content_hash=content_hash(
            holder_name=name, passport_id=passport_id, skills=stored, version=number
        ),
        anchor_status="pending",
        pdf_en_path=None,
        pdf_ka_path=None,
        tx_hash=None,
        issued_at="2026-10-31T11:00:00+00:00",
        skills=stored,
    )
    return StudentUnit(email, passport_id, name, rename, expected, version, source_keys)


def _counts(db: Database) -> tuple[int, int, int, int]:
    return (
        db.count("students"),
        db.count("passport_versions"),
        db.count("skill_entries"),
        db.count("source_records"),
    )


def _sheet_sync(rows: list[dict[str, str]]) -> FakeSheet:
    sheet = FakeSheet(rows)
    result = run_sync(PgSyncStore(), sheet)
    assert result.status == "completed"
    return sheet


# --- the happy path -------------------------------------------------------------------------


def test_a_new_student_is_stored_whole_and_its_hashes_match_the_stored_skills(db: Database) -> None:
    _sheet_sync([ADA, {**ADA, "skill": "SQL", "awarded_on": ""}])
    assert _counts(db) == (1, 1, 2, 2)
    assert find_inconsistencies(db.students_nested()) == []
    assert db.run("select * from sync_inconsistencies()") == ""
    # Positions follow the canonical order the hash was computed over.
    assert db.run("select string_agg(skill, ',' order by position) from skill_entries") == (
        "Python,SQL"
    )


def test_a_second_run_changes_nothing_and_a_new_skill_makes_version_two(db: Database) -> None:
    _sheet_sync([ADA])
    before = db.run("select verification_code, content_hash from passport_versions")
    sheet = _sheet_sync([ADA])
    assert db.run("select verification_code, content_hash from passport_versions") == before
    assert _counts(db)[:2] == (1, 1)
    assert [(o.status, o.version) for o in sheet.writes[0]] == [("SYNCED", "V1")]
    _sheet_sync([ADA, {**ADA, "skill": "Rust", "full_name": "Ada King"}])
    assert _counts(db)[:3] == (1, 2, 3)
    assert db.run("select full_name from students") == "Ada King"
    assert find_inconsistencies(db.students_nested()) == []


def test_a_rename_without_a_skill_change_is_one_atomic_update(db: Database) -> None:
    _sheet_sync([ADA])
    _sheet_sync([{**ADA, "full_name": "Ada King"}])
    assert db.run("select full_name from students") == "Ada King"
    assert db.count("passport_versions") == 1


# --- crashes leave nothing behind -----------------------------------------------------------


def test_a_crash_after_the_skills_are_written_rolls_back_student_version_and_skills(
    db: Database,
) -> None:
    store = PgSyncStore()
    # A NULL record key fails on the last statement, after the student, the version and every
    # skill entry were already inserted in the same transaction.
    crashing = _unit(source_keys=(None,))  # type: ignore[arg-type]
    with pytest.raises(APIError) as caught:
        store.commit_student_unit(crashing)
    assert caught.value.code == "23502"
    assert _counts(db) == (0, 0, 0, 0)


def test_a_crash_on_a_bad_skill_row_rolls_back_the_student_and_the_version(db: Database) -> None:
    store = PgSyncStore()
    missing = (Skill(skill="Python", badge="", awarded_on=None, skill_id="SKL-NOPE"),)
    with pytest.raises(APIError) as caught:
        store.commit_student_unit(_unit(skills=missing))
    assert caught.value.code == "23503"
    assert _counts(db) == (0, 0, 0, 0)


def test_a_crash_on_a_new_version_keeps_the_old_version_and_the_old_name(db: Database) -> None:
    store = PgSyncStore()
    store.commit_student_unit(_unit())
    before = (
        db.run("select full_name from students"),
        db.run("select count(*) from passport_versions"),
    )
    later = (Skill(skill="Rust", badge="", awarded_on=None),)
    broken = _unit(
        number=2,
        expected=1,
        skills=later,
        rename=True,
        name="Ada King",
        code="ZZZZ-ZZZZ-ZZZZ-ZZZZ",
        source_keys=(None,),  # type: ignore[arg-type]
    )
    with pytest.raises(APIError):
        store.commit_student_unit(broken)
    assert (
        db.run("select full_name from students"),
        db.run("select count(*) from passport_versions"),
    ) == before
    assert db.count("skill_entries") == 1


def test_one_failing_student_does_not_stop_or_pollute_the_others(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = sync_mod._unit_payload

    def payload(unit: StudentUnit) -> dict[str, Any]:
        body = real(unit)
        if unit.email == ADA["email"]:
            body["source_keys"] = [None]
        return body

    monkeypatch.setattr(sync_mod, "_unit_payload", payload)
    sheet = FakeSheet([ADA, BOB])
    result = run_sync(PgSyncStore(), sheet)
    assert result.versions_created == 1
    outcomes = {o.index: o for o in sheet.writes[0]}
    assert (outcomes[0].status, outcomes[0].error) == ("FAILED", "sync_error")
    assert outcomes[1].status == "SYNCED"
    assert db.run("select string_agg(email, ',') from students") == BOB["email"]
    assert _counts(db) == (1, 1, 1, 1)
    # The failed student is retried by the next run, whole.
    monkeypatch.undo()
    run_sync(PgSyncStore(), FakeSheet([ADA, BOB]))
    assert _counts(db) == (2, 2, 2, 2)
    assert find_inconsistencies(db.students_nested()) == []


# --- retries, races and refusals ------------------------------------------------------------


def test_retrying_a_committed_unit_is_a_no_op(db: Database) -> None:
    store = PgSyncStore()
    first = store.commit_student_unit(_unit())
    again = store.commit_student_unit(_unit())
    assert (first.created_student, first.created_version) == (True, True)
    assert (again.created_student, again.created_version) == (False, False)
    assert again.skills == first.skills
    assert _counts(db) == (1, 1, 1, 1)


def test_a_unit_built_on_an_old_state_is_refused(db: Database) -> None:
    store = PgSyncStore()
    store.commit_student_unit(_unit())
    later = (Skill(skill="Rust", badge="", awarded_on=None),)
    store.commit_student_unit(_unit(number=2, expected=1, skills=later, code="ZZZZ-ZZZZ-ZZZZ-ZZZZ"))
    other = (Skill(skill="Go", badge="", awarded_on=None),)
    with pytest.raises(APIError) as caught:
        store.commit_student_unit(
            _unit(number=2, expected=1, skills=other, code="YYYY-YYYY-YYYY-YYYY")
        )
    assert caught.value.code == "PS001"
    assert db.count("passport_versions") == 2


def test_two_syncs_racing_on_the_same_student_produce_one_new_version(db: Database) -> None:
    store = PgSyncStore()
    store.commit_student_unit(_unit())
    outcomes: list[str] = []

    def attempt(skill: str, code: str) -> None:
        unit = _unit(
            number=2,
            expected=1,
            skills=(Skill(skill=skill, badge="", awarded_on=None),),
            code=code,
        )
        try:
            PgSyncStore().commit_student_unit(unit)
            outcomes.append("ok")
        except APIError as exc:
            outcomes.append(str(exc.code))

    threads = [
        threading.Thread(target=attempt, args=("Rust", "AAAA-AAAA-AAAA-AAAA")),
        threading.Thread(target=attempt, args=("Go", "BBBB-BBBB-BBBB-BBBB")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["PS001", "ok"]
    assert db.count("passport_versions") == 2
    assert find_inconsistencies(db.students_nested()) == []


def test_an_archived_student_is_refused_and_a_passport_id_mismatch_is_stale(
    db: Database,
) -> None:
    store = PgSyncStore()
    store.commit_student_unit(_unit())
    later = (Skill(skill="Rust", badge="", awarded_on=None),)
    wrong_id = _unit(
        number=2, expected=1, skills=later, code="ZZZZ-ZZZZ-ZZZZ-ZZZZ", passport_id="BTU-00000000BB"
    )
    with pytest.raises(APIError) as stale:
        store.commit_student_unit(wrong_id)
    assert stale.value.code == "PS001"
    db.run("update students set deleted_at = now()")
    with pytest.raises(APIError) as archived:
        store.commit_student_unit(
            _unit(number=2, expected=1, skills=later, code="ZZZZ-ZZZZ-ZZZZ-ZZZZ")
        )
    assert archived.value.code == "PS002"
    assert db.count("passport_versions") == 1


def test_a_malformed_unit_is_refused(db: Database) -> None:
    store = PgSyncStore()
    empty = _unit()
    no_skills = replace(empty, version=replace(empty.version, skills=()))  # type: ignore[type-var]
    with pytest.raises(APIError) as caught:
        store.commit_student_unit(no_skills)
    assert caught.value.code == "PS003"
    skipping = _unit(number=3, expected=0)
    with pytest.raises(APIError) as numbering:
        store.commit_student_unit(skipping)
    assert numbering.value.code == "PS003"
    assert _counts(db) == (0, 0, 0, 0)


def test_the_sheet_reports_a_stale_unit_by_name(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sheet_sync([ADA])
    store = PgSyncStore()
    real = store.current_students

    def old_view() -> dict[str, sync_mod.StudentState]:
        states = real()
        db.run(
            "insert into passport_versions (student_id, version_number, holder_name, "
            "verification_code, verification_id_hash, skill_fingerprint, content_hash) "
            "select id, 2, 'x', 'AAAA-AAAA-AAAA-AAAA', '0x' || repeat('1', 64), "
            "'0x' || repeat('2', 64), '0x' || repeat('3', 64) from students"
        )
        return states

    monkeypatch.setattr(store, "current_students", old_view)
    sheet = FakeSheet([ADA, {**ADA, "skill": "Rust"}])
    run_sync(store, sheet)
    assert {o.error for o in sheet.writes[0]} == {SYNC_STALE}
    assert db.count("passport_versions") == 2


def test_a_hash_mismatch_after_commit_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    real = sync_mod._skills_from_stored

    def altered(value: object) -> tuple[Skill, ...]:
        return (*real(value), Skill(skill="Injected", badge="", awarded_on=None))

    monkeypatch.setattr(sync_mod, "_skills_from_stored", altered)
    sheet = FakeSheet([ADA])
    run_sync(PgSyncStore(), sheet)
    assert sheet.writes[0][0].error == SNAPSHOT_MISMATCH


# --- healing and detecting existing damage --------------------------------------------------


def test_a_student_left_without_a_version_is_healed_by_the_next_sync(db: Database) -> None:
    db.run(
        f"insert into students (email, full_name, passport_id) "
        f"values ('{ADA['email']}', 'Ada Lovelace', '{PASSPORT}')"
    )
    assert "student_without_version" in db.run("select kind from sync_inconsistencies()")
    sheet = _sheet_sync([ADA])
    assert [(o.status, o.version, o.passport_id) for o in sheet.writes[0]] == [
        ("SYNCED", "V1", PASSPORT)
    ]
    assert _counts(db)[:3] == (1, 1, 1)
    assert db.run("select * from sync_inconsistencies()") == ""


def test_the_report_finds_half_written_rows_and_changes_nothing(db: Database) -> None:
    _sheet_sync([ADA, BOB])
    # Damage the way the old sync could: a version without skills, a gap, edited skill text.
    db.run(
        "insert into students (email, full_name, passport_id) "
        "values ('lonely@btu.edu.ge', 'Lonely', 'BTU-00000000CC')"
    )
    db.run(
        "insert into passport_versions (student_id, version_number, holder_name, "
        "verification_code, verification_id_hash, skill_fingerprint, content_hash) "
        "select id, 3, 'Ada Lovelace', 'AAAA-AAAA-AAAA-AAAA', '0x' || repeat('1', 64), "
        "'0x' || repeat('2', 64), '0x' || repeat('3', 64) from students where email = "
        f"'{ADA['email']}'"
    )
    db.run(
        "update skill_entries set skill = 'Tampered' where version_id in "
        f"(select pv.id from passport_versions pv join students s on s.id = pv.student_id "
        f"where s.email = '{BOB['email']}')"
    )
    before = (_counts(db), db.run("select md5(string_agg(t::text, '')) from students t"))
    sql_kinds = set(db.run("select kind from sync_inconsistencies()").split())
    assert sql_kinds == {"student_without_version", "version_without_skills", "version_number_gap"}
    python_kinds = {p.kind for p in find_inconsistencies(db.students_nested())}
    assert python_kinds == sql_kinds | {"skill_fingerprint_mismatch"}
    after = (_counts(db), db.run("select md5(string_agg(t::text, '')) from students t"))
    assert after == before


# --- the migration --------------------------------------------------------------------------


def test_the_migration_can_run_twice_and_only_the_service_role_can_call_the_functions(
    db: Database,
) -> None:
    from pg_support import MIGRATIONS

    sql = (MIGRATIONS / "0011_atomic_sync.sql").read_text(encoding="utf-8")
    db.run(sql)
    db.run(sql)
    for function in ("sync_student_unit(jsonb)", "sync_inconsistencies()"):
        allowed = {
            role: db.run(f"select has_function_privilege('{role}', '{function}', 'execute')")
            for role in ("anon", "authenticated", "service_role")
        }
        assert allowed == {"anon": "f", "authenticated": "f", "service_role": "t"}


def test_the_unit_function_returns_the_stored_snapshot_in_stored_order(db: Database) -> None:
    skills = (
        Skill(skill="B", badge="", awarded_on=None),
        Skill(skill="A", badge="x", awarded_on="2025-01-01", description="d"),
    )
    stored = PgSyncStore().commit_student_unit(_unit(skills=skills))
    # The function stores the skills in the order it is given, which is the hashed order.
    assert [s.skill for s in stored.skills or ()] == ["B", "A"]
    raw = json.loads(db.run("select json_agg(skill order by position) from skill_entries"))
    assert raw == ["B", "A"]
