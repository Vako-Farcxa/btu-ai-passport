from pathlib import Path

import openpyxl
import pytest

from passport_api.fingerprint import content_hash, skill_fingerprint
from passport_api.schemas import Skill
from passport_api.settings import settings
from passport_api.sync import (
    CatalogSkill,
    FakeSheet,
    MemorySyncStore,
    records_from_values,
    run_sync,
)

MIGRATION = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0005_skills_catalog.sql"
)


@pytest.fixture(autouse=True)
def _domains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "allowed_email_domains", "btu.edu.ge, example.org")


def row(skill_id: str | None = "SKL-002", **overrides: str) -> dict[str, str]:
    base = {
        "BTU Email (Test)": "ada@btu.edu.ge",
        "First Name": "Ada",
        "Last Name": "Lovelace",
        "Skill Name": "Prompt Engineering Fundamentals",
        "Skill Category": "AI Skill",
        "Badge/Stamp Code": "BDG-AI-001",
        "Skill Description": "Writing effective prompts.",
        "Date Earned": "2026-10-28",
    }
    if skill_id is not None:
        base["Skill ID"] = skill_id
    base.update(overrides)
    return base


def test_skill_is_upserted_into_the_catalog() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([row()]))
    assert store.skills == {
        "SKL-002": CatalogSkill(
            id="SKL-002",
            name="Prompt Engineering Fundamentals",
            category="AI Skill",
            badge="BDG-AI-001",
            description="Writing effective prompts.",
        )
    }


def test_catalog_row_is_updated_not_duplicated() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([row()]))
    run_sync(store, FakeSheet([row(**{"Skill Description": "Better text."})]))
    assert list(store.skills) == ["SKL-002"]
    assert store.skills["SKL-002"].description == "Better text."


def test_shared_skill_is_one_catalog_row() -> None:
    store = MemorySyncStore()
    other = row(**{"BTU Email (Test)": "bob@btu.edu.ge", "First Name": "Bob"})
    run_sync(store, FakeSheet([row(), other]))
    assert len(store.skills) == 1
    assert len(store.versions) == 2


def test_skill_id_is_saved_on_the_version_skill() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([row(skill_id="skl-002")]))
    (version,) = store.versions
    assert [s.skill_id for s in version.skills] == ["SKL-002"]


def test_missing_skill_id_still_syncs() -> None:
    store = MemorySyncStore()
    result = run_sync(store, FakeSheet([row(skill_id=None)]))
    assert result.status == "completed"
    assert result.versions_created == 1
    assert store.skills == {}
    (version,) = store.versions
    assert [s.skill_id for s in version.skills] == [None]


def test_skill_id_does_not_change_fingerprint_or_content_hash() -> None:
    plain = (Skill(skill="Python", badge="BDG-AI-001", awarded_on="2025-01-15"),)
    linked = (plain[0].model_copy(update={"skill_id": "SKL-001"}),)
    assert skill_fingerprint(plain) == skill_fingerprint(linked)
    first = content_hash(holder_name="Ada", passport_id="BTU-X", skills=plain, version=1)
    second = content_hash(holder_name="Ada", passport_id="BTU-X", skills=linked, version=1)
    assert first == second


def test_adding_skill_ids_to_the_sheet_creates_no_new_version() -> None:
    store = MemorySyncStore()
    run_sync(store, FakeSheet([row(skill_id=None)]))
    (before,) = store.versions
    result = run_sync(store, FakeSheet([row()]))
    assert result.versions_created == 0
    assert len(store.versions) == 1
    assert store.versions[0].skill_fingerprint == before.skill_fingerprint
    assert store.versions[0].content_hash == before.content_hash
    assert "SKL-002" in store.skills


def test_skill_id_is_not_in_the_api_skill_json() -> None:
    skill = Skill(skill="Python", badge="", awarded_on=None, skill_id="SKL-001")
    assert "skill_id" not in skill.model_dump()


def test_migration_creates_catalog_with_rls_and_nullable_link() -> None:
    sql = MIGRATION.read_text()
    assert "create table skills" in sql
    assert "alter table skills enable row level security" in sql
    assert "add column if not exists skill_id text references skills (id)" in sql
    assert "not null" not in sql.split("skill_id text references")[1].splitlines()[0]


def test_official_sheet_skill_ids_fill_the_catalog() -> None:
    fixture = Path(__file__).parent / "fixtures" / "official_test_data.xlsx"
    sheet = openpyxl.load_workbook(fixture).worksheets[0]
    grid: list[list[object]] = [
        ["" if c is None else c for c in r] for r in sheet.iter_rows(values_only=True)
    ]
    _, records = records_from_values(grid)
    store = MemorySyncStore()
    run_sync(store, FakeSheet([{k: str(v) for k, v in r.items()} for r in records]))
    expected = {str(r["Skill ID"]).strip().upper() for r in records if str(r["Skill ID"]).strip()}
    assert expected
    assert set(store.skills) == expected
    saved = {s.skill_id for v in store.versions for s in v.skills}
    assert saved <= expected
    assert saved
