"""The read-only report for students and versions left half-written by the old sync, and the
guard that stops such a version from ever being anchored."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fake_chain import FakeChain
from fastapi.testclient import TestClient

import passport_api.api.admin as admin_mod
from passport_api.anchoring import reconcile_anchors
from passport_api.consistency import find_inconsistencies, load_students
from passport_api.fingerprint import content_hash, skill_fingerprint
from passport_api.main import app
from passport_api.schemas import Skill
from passport_api.sync import MemorySyncStore, SupabaseSyncStore, VersionRecord

client = TestClient(app)
SKILLS = (Skill(skill="Python", badge="Foundation", awarded_on="2025-01-15"),)
PASSPORT = "BTU-00000000AA"


def _entries(skills: tuple[Skill, ...] = SKILLS) -> list[dict[str, Any]]:
    return [
        {
            "skill": s.skill,
            "badge": s.badge,
            "awarded_on": s.awarded_on,
            "description": "",
            "skill_id": None,
            "position": position,
        }
        for position, s in enumerate(skills, start=1)
    ]


def _version(number: int = 1, **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version_number": number,
        "holder_name": "Ada Lovelace",
        "skill_fingerprint": skill_fingerprint(SKILLS),
        "content_hash": content_hash(
            holder_name="Ada Lovelace", passport_id=PASSPORT, skills=SKILLS, version=number
        ),
        "skill_entries": _entries(),
    }
    return {**base, **changes}


def _student(versions: list[dict[str, Any]], **changes: Any) -> dict[str, Any]:
    return {
        "email": "ada@btu.edu.ge",
        "passport_id": PASSPORT,
        "deleted_at": None,
        "passport_versions": versions,
        **changes,
    }


def _kinds(students: list[dict[str, Any]]) -> list[str]:
    return [p.kind for p in find_inconsistencies(students)]


def test_a_healthy_student_has_no_problems() -> None:
    assert _kinds([_student([_version(1), _version(2)])]) == []


def test_an_active_student_without_a_version_is_reported_but_an_archived_one_is_not() -> None:
    assert _kinds([_student([])]) == ["student_without_version"]
    assert _kinds([_student([], deleted_at="2026-10-30T10:00:00+00:00")]) == []


def test_a_version_without_skills_is_reported() -> None:
    problems = find_inconsistencies([_student([_version(1, skill_entries=[])])])
    assert [(p.kind, p.version_number) for p in problems] == [("version_without_skills", 1)]


def test_skills_that_do_not_hash_to_the_stored_hash_are_reported() -> None:
    other = (Skill(skill="Rust", badge="", awarded_on=None),)
    changed = _version(1, skill_entries=_entries(other))
    assert _kinds([_student([changed])]) == ["skill_fingerprint_mismatch"]
    wrong_content = _version(1, content_hash="0x" + "ab" * 32)
    assert _kinds([_student([wrong_content])]) == ["content_hash_mismatch"]


def test_gaps_in_version_numbers_and_skill_positions_are_reported() -> None:
    assert _kinds([_student([_version(1), _version(3)])]) == ["version_number_gap"]
    entries = _entries()
    entries[0]["position"] = 2
    assert _kinds([_student([_version(1, skill_entries=entries)])]) == ["skill_position_gap"]


def test_the_report_never_writes() -> None:
    with patch("passport_api.consistency.get_supabase") as db:
        page = db.return_value.table.return_value.select.return_value.order.return_value
        page.range.return_value.execute.return_value.data = [_student([])]
        load_students()
    table = db.return_value.table.return_value
    for write in ("insert", "update", "upsert", "delete"):
        assert not getattr(table, write).called


def test_students_are_loaded_page_by_page() -> None:
    page = [_student([_version(1)]) for _ in range(500)]
    with patch("passport_api.consistency.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value.order.return_value
        query.range.return_value.execute.side_effect = [
            MagicMock(data=page),
            MagicMock(data=page[:3]),
        ]
        students = load_students()
    assert len(students) == 503
    assert [call.args for call in query.range.call_args_list] == [(0, 499), (500, 999)]


def test_the_admin_endpoint_returns_the_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    monkeypatch.setattr(admin_mod, "load_students", lambda: [_student([]), _student([_version()])])
    response = client.get("/admin/consistency", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    assert response.json() == {
        "students_checked": 2,
        "problems": [
            {
                "kind": "student_without_version",
                "passport_id": PASSPORT,
                "version_number": None,
                "detail": (
                    "Active student with no passport version. The next sync creates version 1."
                ),
            }
        ],
    }


def test_the_admin_endpoint_needs_an_admin() -> None:
    assert client.get("/admin/consistency").status_code in (401, 403)


# --- the anchoring guard --------------------------------------------------------------------


def _pending(db: MagicMock, rows: list[dict[str, Any]]) -> None:
    query = db.return_value.table.return_value.select.return_value.in_.return_value
    query.order.return_value.execute.return_value.data = rows


def _db_row(**changes: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "aaaaaaaa-0001-4000-8000-000000000001",
        "version_number": 1,
        "holder_name": "Ada Lovelace",
        "verification_code": "ABCD-EFGH-JKMN-PQRS",
        "verification_id_hash": "0x" + "22" * 32,
        "skill_fingerprint": skill_fingerprint(SKILLS),
        "content_hash": content_hash(
            holder_name="Ada Lovelace", passport_id=PASSPORT, skills=SKILLS, version=1
        ),
        "anchor_status": "pending",
        "tx_hash": None,
        "anchored_at": None,
        "issued_at": "2026-10-31T11:00:00+00:00",
        "skill_entries": _entries(),
        "students": {"email": "ada@btu.edu.ge", "passport_id": PASSPORT},
    }
    return {**row, **changes}


def test_a_database_version_that_matches_its_hash_has_no_snapshot_error() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        _pending(db, [_db_row()])
        (record,) = SupabaseSyncStore().pending_anchors()
    assert record.snapshot_error is None


def test_a_version_whose_skills_do_not_match_its_hash_is_never_sent_to_the_chain() -> None:
    broken = _db_row(skill_entries=[])
    with patch("passport_api.sync.get_supabase") as db:
        _pending(db, [broken])
        (record,) = SupabaseSyncStore().pending_anchors()
    assert record.snapshot_error == "no_skills"
    store = MemorySyncStore()
    store.versions.append(record)
    chain = FakeChain()
    result = reconcile_anchors(store, chain, now=datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
    assert chain.sent == []
    assert (record.anchor_status, record.anchor_last_error) == (
        "failed_permanent",
        "snapshot_mismatch",
    )
    assert result.failed_permanent == 1


def test_an_admin_retry_cannot_send_a_mismatching_version_either() -> None:
    broken = replace(_version_record(), snapshot_error="content_hash_mismatch")
    store = MemorySyncStore()
    store.versions.append(broken)
    chain = FakeChain()
    reconcile_anchors(store, chain, only=[broken], force=True)
    assert chain.sent == []
    assert broken.anchor_last_error == "snapshot_mismatch"


def _version_record() -> VersionRecord:
    return VersionRecord(
        passport_id=PASSPORT,
        email="ada@btu.edu.ge",
        version_number=1,
        holder_name="Ada Lovelace",
        verification_code="ABCD-EFGH-JKMN-PQRS",
        verification_id_hash="0x" + "22" * 32,
        skill_fingerprint="0x" + "33" * 32,
        content_hash="0x" + "11" * 32,
        anchor_status="pending",
        pdf_en_path=None,
        pdf_ka_path=None,
        tx_hash=None,
        issued_at="2026-10-31T11:00:00+00:00",
        skills=(),
    )
