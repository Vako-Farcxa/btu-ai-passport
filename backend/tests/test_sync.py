import ast
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from passport_api.api.sync import get_sheet, get_sync_store
from passport_api.main import app
from passport_api.schemas import Skill
from passport_api.settings import settings
from passport_api.sync import FakeSheet, MemorySyncStore, run_sync

client = TestClient(app)
PASSPORT_ID = re.compile(r"^BTU-[0-9A-HJKMNP-TV-Z]{10}$")
VERIFICATION_CODE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{4}(?:-[0-9A-HJKMNP-TV-Z]{4}){3}$")
HASH = re.compile(r"^0x[0-9a-f]{64}$")
REPO_ROOT = Path(__file__).resolve().parents[2]


def sheet_row(
    email: str,
    full_name: str,
    skill: str,
    badge: str = "",
    awarded_on: str = "",
) -> dict[str, str]:
    return {
        "email": email,
        "full_name": full_name,
        "skill": skill,
        "badge": badge,
        "awarded_on": awarded_on,
    }


def test_same_skill_facts_do_not_create_another_version() -> None:
    store = MemorySyncStore()
    rows = [
        sheet_row("ada@btu.edu.ge", "Ada Lovelace", "SQL", "Core", "2024-02-02"),
        sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Python", "Foundation", "2025-01-15"),
    ]
    first = run_sync(store, FakeSheet(rows))
    second = run_sync(store, FakeSheet(list(reversed(rows))))
    assert first.status == "completed"
    assert first.versions_created == 1
    assert first.rows_read == 2
    assert second.versions_created == 0
    assert len(store.versions) == 1
    assert store.versions[0].version_number == 1
    assert store.students[0].passport_id == store.versions[0].passport_id


def test_skill_badge_or_date_change_creates_one_next_version() -> None:
    store = MemorySyncStore()
    original = [sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Python", "Foundation", "2025-01-15")]
    run_sync(store, FakeSheet(original))
    for updated in (
        [sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Rust", "Foundation", "2025-01-15")],
        [sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Rust", "Stamp", "2025-01-15")],
        [sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Rust", "Stamp", "2025-06-01")],
    ):
        result = run_sync(store, FakeSheet(updated))
        assert result.versions_created == 1
    assert [version.version_number for version in store.versions] == [1, 2, 3, 4]
    assert len(store.students) == 1


def test_several_unseen_edits_create_one_version() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")]))
    result = run_sync(
        store,
        FakeSheet(
            [
                sheet_row("ada@btu.edu.ge", "Ada", "Python"),
                sheet_row("ada@btu.edu.ge", "Ada", "SQL", "Core", "2024-02-02"),
                sheet_row("ada@btu.edu.ge", "Ada", "Rust"),
            ]
        ),
    )
    assert result.versions_created == 1
    assert store.versions[-1].version_number == 2
    assert len(store.versions[-1].skills) == 3


def test_removed_skill_creates_one_version() -> None:
    store = MemorySyncStore()
    run_sync(
        store,
        FakeSheet(
            [
                sheet_row("ada@btu.edu.ge", "Ada", "Python"),
                sheet_row("ada@btu.edu.ge", "Ada", "SQL"),
            ]
        ),
    )
    result = run_sync(store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")]))
    assert result.versions_created == 1
    assert store.versions[-1].skills == (Skill(skill="Python", badge="", awarded_on=None),)


def test_name_only_edit_updates_student_and_freezes_holder_name() -> None:
    store = MemorySyncStore()
    run_sync(
        store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Python", "Foundation")])
    )
    result = run_sync(
        store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada King", "Python", "Foundation")])
    )
    assert result.versions_created == 0
    assert len(store.versions) == 1
    assert store.students[0].full_name == "Ada King"
    assert store.versions[0].holder_name == "Ada Lovelace"


def test_new_email_creates_a_new_passport_id() -> None:
    store = MemorySyncStore()
    result = run_sync(
        store,
        FakeSheet(
            [
                sheet_row("ada@btu.edu.ge", "Ada", "Python"),
                sheet_row("grace@btu.edu.ge", "Grace", "SQL"),
            ]
        ),
    )
    assert result.versions_created == 2
    ids = [student.passport_id for student in store.students]
    assert len(set(ids)) == 2
    assert all(PASSPORT_ID.fullmatch(passport_id) for passport_id in ids)
    again = run_sync(
        store,
        FakeSheet(
            [
                sheet_row("ada@btu.edu.ge", "Ada", "Python"),
                sheet_row("grace@btu.edu.ge", "Grace", "SQL"),
            ]
        ),
    )
    assert again.versions_created == 0
    assert [student.passport_id for student in store.students] == ids


def test_disappeared_email_leaves_the_old_passport() -> None:
    store = MemorySyncStore()
    run_sync(
        store,
        FakeSheet(
            [
                sheet_row("ada@btu.edu.ge", "Ada", "Python"),
                sheet_row("grace@btu.edu.ge", "Grace", "SQL"),
            ]
        ),
    )
    grace_id = next(
        student.passport_id for student in store.students if student.email == "grace@btu.edu.ge"
    )
    result = run_sync(store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")]))
    assert result.versions_created == 0
    kept = next(student for student in store.students if student.email == "grace@btu.edu.ge")
    assert kept.passport_id == grace_id
    assert any(version.passport_id == grace_id for version in store.versions)


def test_new_version_stays_pending_with_both_pdfs() -> None:
    store = MemorySyncStore()
    run_sync(
        store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python", "Foundation", "2025-01-15")])
    )
    version = store.versions[0]
    assert version.anchor_status == "pending"
    assert version.pdf_en_path == f"{version.passport_id}/v{version.version_number}/en.pdf"
    assert version.pdf_ka_path == f"{version.passport_id}/v{version.version_number}/ka.pdf"
    assert version.tx_hash is None
    assert VERIFICATION_CODE.fullmatch(version.verification_code)
    assert HASH.fullmatch(version.verification_id_hash)
    assert HASH.fullmatch(version.skill_fingerprint)
    assert HASH.fullmatch(version.content_hash)
    assert version.skills == (Skill(skill="Python", badge="Foundation", awarded_on="2025-01-15"),)


def test_rows_are_grouped_and_invalid_rows_are_ignored() -> None:
    store = MemorySyncStore()
    rows = [
        {" Email ": "", "Full_Name": "Nobody", "Skill": "Python", "Badge": "", "Awarded_On": ""},
        {
            "email": "ada@btu.edu.ge",
            "full_name": "Ada",
            "skill": "   ",
            "badge": "",
            "awarded_on": "",
        },
        {
            "email": "ada@gmail.com",
            "full_name": "Ada",
            "skill": "Python",
            "badge": "",
            "awarded_on": "",
        },
        {
            "email": "  Ada@BTU.edu.ge ",
            "full_name": "Ada Lovelace",
            "skill": "Python",
            "badge": "",
            "awarded_on": "soon",
        },
        {
            "email": "ada@btu.edu.ge",
            "full_name": "Ada Lovelace",
            "skill": "Python",
            "badge": "",
            "awarded_on": "soon",
        },
        {
            "email": "ada@btu.edu.ge",
            "full_name": "Ada Lovelace",
            "skill": "SQL",
            "badge": "Core",
            "awarded_on": "",
        },
        sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Alpha", "", ""),
        sheet_row("ada@btu.edu.ge", "Ada Lovelace", "Alpha", "", "2020-01-01"),
    ]
    result = run_sync(store, FakeSheet(rows))
    assert result.rows_read == len(rows)
    assert result.versions_created == 1
    assert len(store.students) == 1
    assert store.students[0].email == "ada@btu.edu.ge"
    assert store.versions[0].holder_name == "Ada Lovelace"
    assert store.versions[0].skills == (
        Skill(skill="Alpha", badge="", awarded_on="2020-01-01"),
        Skill(skill="Alpha", badge="", awarded_on=None),
        Skill(skill="Python", badge="", awarded_on=None),
        Skill(skill="SQL", badge="Core", awarded_on=None),
    )


def test_failed_sheet_read_commits_nothing() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")]))
    before = (store.students[0].full_name, len(store.versions), store.versions[0].verification_code)
    failed = FakeSheet(error=RuntimeError("sheet down"))
    result = run_sync(store, failed)
    assert failed.reads == 1
    assert result.status == "failed"
    assert result.error == "sheet_unavailable"
    assert result.rows_read == 0
    assert result.versions_created == 0
    assert (
        store.students[0].full_name,
        len(store.versions),
        store.versions[0].verification_code,
    ) == before
    assert store.has_running() is False
    recovered = run_sync(store, FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")]))
    assert recovered.status == "completed"
    assert recovered.versions_created == 0


def test_second_run_while_running_is_skipped_without_reading() -> None:
    store = MemorySyncStore()
    assert store.try_acquire() is True
    sheet = FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")])
    result = run_sync(store, sheet)
    assert result.status == "skipped"
    assert result.rows_read == 0
    assert result.versions_created == 0
    assert result.error is None
    assert sheet.reads == 0
    assert store.students == []
    assert store.has_running() is True


def test_wrong_or_missing_sync_token_is_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sync_token", "expected-sync-token")
    sheet = FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")])
    store = MemorySyncStore()
    app.dependency_overrides[get_sheet] = lambda: sheet
    app.dependency_overrides[get_sync_store] = lambda: store
    try:
        missing = client.post("/internal/sync")
        wrong = client.post("/internal/sync", headers={"X-Sync-Token": "nope"})
        assert missing.status_code == 401
        assert missing.json() == {"code": "sync_unauthorized"}
        assert wrong.status_code == 401
        assert wrong.json() == {"code": "sync_unauthorized"}
        assert sheet.reads == 0
        assert store.students == []
    finally:
        app.dependency_overrides.clear()


def test_authorized_sync_returns_the_contract_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sync_token", "expected-sync-token")
    sheet = FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "Python")])
    store = MemorySyncStore()
    app.dependency_overrides[get_sheet] = lambda: sheet
    app.dependency_overrides[get_sync_store] = lambda: store
    try:
        response = client.post("/internal/sync", headers={"X-Sync-Token": "expected-sync-token"})
        assert store.try_acquire() is True
        overlapping = FakeSheet([sheet_row("ada@btu.edu.ge", "Ada", "SQL")])
        app.dependency_overrides[get_sheet] = lambda: overlapping
        skipped = client.post("/internal/sync", headers={"X-Sync-Token": "expected-sync-token"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "rows_read": 1,
        "versions_created": 1,
        "error": None,
    }
    assert skipped.status_code == 200
    assert skipped.json() == {
        "status": "skipped",
        "rows_read": 0,
        "versions_created": 0,
        "error": None,
    }
    assert overlapping.reads == 0


def test_sync_imports_pdf_and_chain() -> None:
    source = (REPO_ROOT / "backend" / "src" / "passport_api" / "sync.py").read_text()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "passport_api.pdf" in imported
    assert "passport_api.chain" in imported


def test_main_starts_no_background_sync() -> None:
    source_path = REPO_ROOT / "backend" / "src" / "passport_api" / "main.py"
    tree = ast.parse(source_path.read_text())
    banned = {"create_task", "ensure_future", "run_in_executor"}
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            raise AssertionError("main.py must not poll")
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "lifespan":
            raise AssertionError("main.py must not start a lifespan sync")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in banned
    assert app.router.on_startup == []
    assert app.router.on_shutdown == []


def test_github_workflow_is_the_only_scheduler() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "sync.yml").read_text()
    assert "*/15 * * * *" in workflow
    assert "workflow_dispatch" in workflow
    assert "${{ secrets.SYNC_URL }}/internal/sync" in workflow
    assert "X-Sync-Token: ${{ secrets.SYNC_TOKEN }}" in workflow
    assert "--fail-with-body" in workflow
    assert "expected-sync-token" not in workflow
