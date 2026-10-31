"""Each student's sync is one unit: student, new version, skill snapshot and source rows commit
together or not at all. These run on the in-memory store, which follows the same rules as the
sync_student_unit SQL function (the SQL itself is tested in test_sync_postgres.py)."""

from dataclasses import replace
from typing import Any
from unittest.mock import patch

import pytest

from passport_api.anchoring import SNAPSHOT_MISMATCH
from passport_api.fingerprint import content_hash, skill_fingerprint
from passport_api.schemas import Skill
from passport_api.sync import (
    SYNC_STALE,
    FakeSheet,
    MemorySyncStore,
    StudentRecord,
    StudentUnit,
    SupabaseSyncStore,
    UnitResult,
    VersionRecord,
    run_sync,
    snapshot_problem,
)

ADA = {
    "email": "ada@btu.edu.ge",
    "full_name": "Ada Lovelace",
    "skill": "Python",
    "badge": "Foundation",
    "awarded_on": "2025-01-15",
}
BOB = {**ADA, "email": "bob@btu.edu.ge", "full_name": "Bob Stone"}


@pytest.fixture(autouse=True)
def _no_pdf_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr("passport_api.settings.settings.pdf_storage_dir", str(tmp_path))


def _hashes_match_stored_skills(store: MemorySyncStore) -> None:
    for version in store.versions:
        assert (
            snapshot_problem(
                holder_name=version.holder_name,
                passport_id=version.passport_id,
                version_number=version.version_number,
                skills=version.skills,
                skill_fingerprint_value=version.skill_fingerprint,
                content_hash_value=version.content_hash,
            )
            is None
        )


def test_every_stored_version_hashes_from_exactly_its_stored_skills() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([ADA, {**ADA, "skill": "SQL", "awarded_on": ""}, BOB]))
    run_sync(store, FakeSheet([ADA, {**ADA, "skill": "Rust"}, BOB]))
    assert len(store.versions) == 3
    _hashes_match_stored_skills(store)
    ada2 = max(
        (v for v in store.versions if v.email == ADA["email"]), key=lambda v: v.version_number
    )
    assert ada2.version_number == 2
    assert ada2.content_hash == content_hash(
        holder_name="Ada Lovelace", passport_id=ada2.passport_id, skills=ada2.skills, version=2
    )
    assert ada2.skill_fingerprint == skill_fingerprint(ada2.skills)


def test_a_crash_while_writing_the_unit_leaves_no_partial_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemorySyncStore()

    def crash(unit: StudentUnit) -> None:
        raise RuntimeError("connection lost")

    # The student and the version are staged before the source rows. Dying there must undo both.
    monkeypatch.setattr(store, "_remember_sources", crash)
    sheet = FakeSheet([ADA])
    result = run_sync(store, sheet)
    assert result.status == "completed"
    assert result.versions_created == 0
    assert (store.students, store.versions, store._sources) == ([], [], {})
    assert [(o.status, o.error) for o in sheet.writes[0]] == [("FAILED", "sync_error")]


def test_a_crash_on_a_new_version_keeps_the_old_one_and_the_old_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([ADA]))
    before = (store.students[0].full_name, list(store.versions))

    def crash(unit: StudentUnit) -> None:
        raise RuntimeError("connection lost")

    monkeypatch.setattr(store, "_remember_sources", crash)
    renamed = {**ADA, "full_name": "Ada King", "skill": "Rust"}
    result = run_sync(store, FakeSheet([renamed]))
    assert result.versions_created == 0
    # Neither the new name nor the new version was kept.
    assert (store.students[0].full_name, store.versions) == before
    monkeypatch.undo()
    # The next run does the whole unit.
    again = run_sync(store, FakeSheet([renamed]))
    assert again.versions_created == 1
    assert store.students[0].full_name == "Ada King"
    assert [v.version_number for v in store.versions] == [1, 2]
    _hashes_match_stored_skills(store)


def test_a_skill_missing_from_the_catalog_rolls_the_whole_unit_back() -> None:
    store = MemorySyncStore()
    sheet = FakeSheet([{**ADA, "skill_id": "SKL-404"}])
    with patch.object(store, "upsert_skills"):  # the catalog write is not part of the unit
        run_sync(store, sheet)
    assert (store.students, store.versions) == ([], [])
    assert sheet.writes[0][0].error == "sync_error"


def test_a_retry_of_a_committed_unit_changes_nothing() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([ADA]))
    version = store.versions[0]
    unit = StudentUnit(
        email=ADA["email"],
        passport_id=version.passport_id,
        full_name="Ada Lovelace",
        rename=False,
        expected_latest=0,
        version=replace(version),
        source_keys=("k1",),
    )
    again = store.commit_student_unit(unit)
    assert (again.created_student, again.created_version) == (False, False)
    assert again.version_number == 1
    assert len(store.versions) == 1


def test_a_stale_unit_is_refused_and_writes_nothing() -> None:
    from postgrest.exceptions import APIError

    store = MemorySyncStore()
    run_sync(store, FakeSheet([ADA]))
    stored = store.versions[0]
    skills = (Skill(skill="Rust", badge="", awarded_on=None),)
    new = replace(
        stored,
        version_number=2,
        skill_fingerprint=skill_fingerprint(skills),
        verification_code="ZZZZ-ZZZZ-ZZZZ-ZZZZ",
        skills=skills,
    )
    # Built when version 0 was the latest, but version 1 exists by now.
    stale = StudentUnit(ADA["email"], stored.passport_id, "Ada Lovelace", False, 0, new, ())
    with pytest.raises(APIError) as caught:
        store.commit_student_unit(stale)
    assert caught.value.code == "PS001"
    assert len(store.versions) == 1


def test_an_archived_student_is_refused_inside_the_unit() -> None:
    from postgrest.exceptions import APIError

    store = MemorySyncStore()
    store.students.append(StudentRecord(ADA["email"], "Ada", "BTU-00000000AA", archived=True))
    unit = StudentUnit(ADA["email"], "BTU-00000000AA", "Ada", False, 0, None, ())
    with pytest.raises(APIError) as caught:
        store.commit_student_unit(unit)
    assert caught.value.code == "PS002"


def test_a_stale_unit_is_reported_to_the_sheet_and_retried_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from postgrest.exceptions import APIError

    store = MemorySyncStore()
    original = store.commit_student_unit
    calls = {"n": 0}

    def once_stale(unit: StudentUnit) -> UnitResult:
        calls["n"] += 1
        if calls["n"] == 1:
            raise APIError({"code": "PS001", "message": "sync_unit_stale"})
        return original(unit)

    monkeypatch.setattr(store, "commit_student_unit", once_stale)
    first, second = FakeSheet([ADA]), FakeSheet([ADA])
    run_sync(store, first)
    assert first.writes[0][0].error == SYNC_STALE
    run_sync(store, second)
    assert (second.writes[0][0].status, second.writes[0][0].version) == ("SYNCED", "V1")


def test_stored_skills_that_do_not_match_the_hash_are_caught_after_the_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemorySyncStore()
    original = store.commit_student_unit

    def tampered(unit: StudentUnit) -> UnitResult:
        result = original(unit)
        other = (Skill(skill="Something else", badge="", awarded_on=None),)
        return replace(result, skills=other)

    monkeypatch.setattr(store, "commit_student_unit", tampered)
    sheet = FakeSheet([ADA])
    result = run_sync(store, sheet)
    assert result.versions_created == 0
    assert sheet.writes[0][0].error == SNAPSHOT_MISMATCH


def test_sheet_write_back_is_retried_by_the_next_run_with_the_same_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemorySyncStore()

    class FlakySheet(FakeSheet):
        def __init__(self) -> None:
            super().__init__([ADA, BOB])
            self.fail_next = True

        def write_back(self, outcomes: Any) -> None:
            if self.fail_next:
                self.fail_next = False
                raise ConnectionError("sheets 503")
            super().write_back(outcomes)

    sheet = FlakySheet()
    first = run_sync(store, sheet)
    # The database is committed even though the write-back failed.
    assert first.status == "completed"
    assert first.versions_created == 2
    assert sheet.writes == []
    snapshot = [(v.email, v.version_number, v.verification_code) for v in store.versions]
    second = run_sync(store, sheet)
    assert second.versions_created == 0
    assert [(v.email, v.version_number, v.verification_code) for v in store.versions] == snapshot
    written = {(o.index, o.status, o.version, o.passport_id) for o in sheet.writes[0]}
    assert written == {
        (0, "SYNCED", "V1", store.versions[0].passport_id),
        (1, "SYNCED", "V1", store.versions[1].passport_id),
    }
    # A third write-back repeats exactly the same cells.
    run_sync(store, sheet)
    again = {(o.index, o.status, o.version, o.passport_id) for o in sheet.writes[1]}
    assert again == written


def test_write_back_only_happens_after_the_unit_commits() -> None:
    store = MemorySyncStore()
    seen: list[int] = []

    class WatchingSheet(FakeSheet):
        def write_back(self, outcomes: Any) -> None:
            seen.append(len(store.versions))
            super().write_back(outcomes)

    run_sync(store, WatchingSheet([ADA, BOB]))
    assert seen == [2]


def test_the_unit_keeps_a_rename_with_an_unchanged_skill_set() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([ADA]))
    result = run_sync(store, FakeSheet([{**ADA, "full_name": "Ada King"}]))
    assert result.versions_created == 0
    assert store.students[0].full_name == "Ada King"
    assert len(store.versions) == 1


def test_a_student_row_without_versions_is_healed_and_keeps_its_passport_id() -> None:
    store = MemorySyncStore()
    store.students.append(StudentRecord(ADA["email"], "Ada Lovelace", "BTU-00000000AA"))
    sheet = FakeSheet([ADA])
    result = run_sync(store, sheet)
    assert result.versions_created == 1
    assert [v.passport_id for v in store.versions] == ["BTU-00000000AA"]
    assert store.versions[0].version_number == 1
    assert sheet.writes[0][0].status == "SYNCED"
    _hashes_match_stored_skills(store)


# --- the Supabase store: one RPC per unit ---------------------------------------------------


def _unit() -> StudentUnit:
    skills = (Skill(skill="Python", badge="Foundation", awarded_on="2025-01-15"),)
    version = VersionRecord(
        passport_id="BTU-00000000AA",
        email="ada@btu.edu.ge",
        version_number=1,
        holder_name="Ada Lovelace",
        verification_code="ABCD-EFGH-JKMN-PQRS",
        verification_id_hash="0x" + "22" * 32,
        skill_fingerprint=skill_fingerprint(skills),
        content_hash="0x" + "11" * 32,
        anchor_status="pending",
        pdf_en_path=None,
        pdf_ka_path=None,
        tx_hash=None,
        issued_at="2026-10-31T11:00:00+00:00",
        skills=skills,
    )
    return StudentUnit(
        "ada@btu.edu.ge", "BTU-00000000AA", "Ada Lovelace", False, 0, version, ("k1", "k2")
    )


def test_the_supabase_store_commits_a_unit_with_one_rpc_and_no_table_writes() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        db.return_value.rpc.return_value.execute.return_value.data = {
            "passport_id": "BTU-00000000AA",
            "version_number": 1,
            "holder_name": "Ada Lovelace",
            "created_student": True,
            "created_version": True,
            "skills": [
                {
                    "skill": "Python",
                    "badge": "Foundation",
                    "awarded_on": "2025-01-15",
                    "description": "",
                    "skill_id": None,
                }
            ],
        }
        result = SupabaseSyncStore().commit_student_unit(_unit())
    db.return_value.rpc.assert_called_once()
    name, params = db.return_value.rpc.call_args.args
    assert name == "sync_student_unit"
    payload = params["p_unit"]
    assert payload["expected_latest"] == 0
    assert payload["source_keys"] == ["k1", "k2"]
    assert payload["version"]["skills"] == [
        {
            "skill": "Python",
            "badge": "Foundation",
            "awarded_on": "2025-01-15",
            "description": "",
            "skill_id": None,
        }
    ]
    db.return_value.table.assert_not_called()
    assert (result.created_student, result.created_version, result.version_number) == (
        True,
        True,
        1,
    )
    assert result.skills == _unit().version.skills  # type: ignore[union-attr]


def test_the_supabase_store_has_no_separate_write_methods_left() -> None:
    for name in ("insert_student", "insert_version", "save_student_name", "remember_source"):
        assert not hasattr(SupabaseSyncStore, name)
