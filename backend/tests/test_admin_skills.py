"""Skills catalog and award endpoints, with the Google Sheet and the database mocked."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import passport_api.api.admin as admin_mod
from passport_api.api.admin import get_admin_sheet
from passport_api.api.sync import get_sync_store
from passport_api.main import app
from passport_api.settings import settings
from passport_api.sheet_admin import (
    ALREADY_AWARDED,
    MISSING_FULL_NAME,
    AwardInput,
    AwardPlacement,
    build_award_rows,
)
from passport_api.sync import (
    SKILLS_HEADER,
    CatalogSkill,
    FakeSheet,
    MemorySyncStore,
    RowOutcome,
    SheetUnavailableError,
    catalog_from_values,
    find_header_row,
    records_from_values,
    run_sync,
)

client = TestClient(app)
AUTH = {"Authorization": "Bearer fake"}

HEADER = [
    "Student ID",
    "First Name",
    "Last Name",
    "BTU Email (Test)",
    "Program",
    "Education Level",
    "Passport ID (Existing)",
    "First Issued (Existing)",
    "Student Status",
    "Record ID",
    "Skill ID",
    "Skill Name",
    "Skill Category",
    "Badge/Stamp Code",
    "Skill Description",
    "Date Earned",
    "Passport Sync Status",
    "Synced Passport Version",
    "Synced At (UTC)",
    "Sync Error / Notes",
]


def existing_row(email: str = "ada@btu.edu.ge", skill_id: str = "SKL-001") -> list[str]:
    return [
        "BTU-T-0001",
        "Ada",
        "Lovelace",
        email,
        "Computer Science",
        "Bachelor's",
        "BTU-AI-000125",
        "2026-09-15",
        "Active",
        "REC-0007",
        skill_id,
        "AI Literacy",
        "AI Skill",
        "BDG-AI-001",
        "Fundamentals.",
        "2026-09-18",
        "SYNCED",
        "V1",
        "2026-10-01 10:00 UTC",
        "",
    ]


def award(email: str = "new@btu.edu.ge", **overrides: str) -> AwardInput:
    values = {
        "email": email,
        "first_name": "",
        "last_name": "",
        "skill_id": "SKL-002",
        "skill_name": "Prompt Engineering Fundamentals",
        "category": "AI Skill",
        "badge": "BDG-AI-001",
        "description": "Writing prompts.",
        "awarded_on": "2026-10-28",
    }
    values.update(overrides)
    return AwardInput(**values)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_catalog_from_values_reads_the_skills_tab() -> None:
    grid: list[list[object]] = [
        list(SKILLS_HEADER),
        ["skl-001", "AI Literacy", "AI წიგნიერება", "AI Skill", "Basics."],
        ["SKL-002", "Prompting", "", "AI Applied Skill", ""],
        ["", "No id", "", "", ""],
    ]
    skills = catalog_from_values(grid)
    assert [s.id for s in skills] == ["SKL-001", "SKL-002"]
    assert skills[0].name_ka == "AI წიგნიერება"
    assert skills[0].badge == "BDG-AI-001"
    assert skills[1].badge == "BDG-AI-002"
    assert catalog_from_values([["nothing", "here"]]) == []


def test_new_student_row_follows_the_official_layout() -> None:
    rows, placements = build_award_rows(
        HEADER,
        [existing_row()],
        [award(first_name="Nino", last_name="Beridze")],
        set(),
        first_row=6,
    )
    assert placements == [AwardPlacement("new@btu.edu.ge", 6, "")]
    row = dict(zip(HEADER, rows[0], strict=True))
    assert row["First Name"] == "Nino"
    assert row["Last Name"] == "Beridze"
    assert row["BTU Email (Test)"] == "new@btu.edu.ge"
    assert row["Student Status"] == "Active"
    assert row["Passport ID (Existing)"] == ""
    assert row["Record ID"] == "REC-0008"
    assert row["Skill ID"] == "SKL-002"
    assert row["Skill Name"] == "Prompt Engineering Fundamentals"
    assert row["Skill Category"] == "AI Skill"
    assert row["Badge/Stamp Code"] == "BDG-AI-001"
    assert row["Date Earned"] == "2026-10-28"
    # Sync output columns stay empty. The sync writes them.
    assert [row[name] for name in HEADER[-4:]] == ["", "", "", ""]
    assert len(rows[0]) == len(HEADER)


def test_existing_student_keeps_name_and_passport_id() -> None:
    rows, placements = build_award_rows(
        HEADER, [existing_row()], [award("ADA@btu.edu.ge")], set(), first_row=6
    )
    row = dict(zip(HEADER, rows[0], strict=True))
    assert placements[0].row_number == 6
    assert row["First Name"] == "Ada"
    assert row["Program"] == "Computer Science"
    assert row["Passport ID (Existing)"] == "BTU-AI-000125"
    assert row["Skill ID"] == "SKL-002"


def test_already_awarded_and_missing_name_are_not_written() -> None:
    rows, placements = build_award_rows(
        HEADER,
        [existing_row(skill_id="SKL-002")],
        [award("ada@btu.edu.ge"), award("nobody@btu.edu.ge")],
        set(),
        first_row=6,
    )
    assert rows == []
    assert [p.error for p in placements] == [ALREADY_AWARDED, MISSING_FULL_NAME]
    assert all(p.row_number is None for p in placements)


def test_known_database_student_needs_no_name() -> None:
    rows, placements = build_award_rows(
        HEADER, [], [award("db@btu.edu.ge")], {"db@btu.edu.ge"}, first_row=5
    )
    assert len(rows) == 1
    assert placements[0].row_number == 5


def test_two_awards_get_consecutive_rows_and_record_ids() -> None:
    rows, placements = build_award_rows(
        HEADER,
        [existing_row()],
        [award("a@btu.edu.ge", first_name="A"), award("b@btu.edu.ge", first_name="B")],
        set(),
        first_row=10,
    )
    assert [p.row_number for p in placements] == [10, 11]
    assert [r[HEADER.index("Record ID")] for r in rows] == ["REC-0008", "REC-0009"]


def test_old_five_column_layout() -> None:
    header = ["email", "full_name", "skill", "badge", "awarded_on"]
    rows, _ = build_award_rows(
        header, [], [award(first_name="Nino", last_name="Beridze")], set(), first_row=2
    )
    assert rows == [
        [
            "new@btu.edu.ge",
            "Nino Beridze",
            "Prompt Engineering Fundamentals",
            "BDG-AI-001",
            "2026-10-28",
        ]
    ]


# ---------------------------------------------------------------------------
# The sync prefers the Skills tab for the catalog
# ---------------------------------------------------------------------------


class TabSheet(FakeSheet):
    def __init__(self, rows: list[dict[str, str]], tab: list[CatalogSkill]) -> None:
        super().__init__(rows)
        self.tab = tab

    def read_catalog(self) -> list[CatalogSkill]:
        return self.tab


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "allowed_email_domains", "btu.edu.ge")
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))


def test_sync_stores_tab_catalog_over_award_row_text() -> None:
    store = MemorySyncStore()
    rows = [
        {
            "BTU Email (Test)": "ada@btu.edu.ge",
            "First Name": "Ada",
            "Last Name": "Lovelace",
            "Skill ID": "SKL-002",
            "Skill Name": "Old name",
            "Skill Category": "AI Skill",
            "Date Earned": "2026-10-28",
        }
    ]
    tab = [
        CatalogSkill("SKL-002", "New name", "AI Skill", "BDG-AI-001", "Edited.", name_ka="ახალი")
    ]
    run_sync(store, TabSheet(rows, tab))
    assert store.skills["SKL-002"].name == "New name"
    assert store.skills["SKL-002"].name_ka == "ახალი"
    # The passport keeps the text from the award row. Only the catalog changed.
    assert store.versions[0].skills[0].skill == "Old name"


def test_sync_ignores_a_failing_tab_read() -> None:
    class Broken(TabSheet):
        def read_catalog(self) -> list[CatalogSkill]:
            raise SheetUnavailableError("sheet_unavailable")

    store = MemorySyncStore()
    result = run_sync(store, Broken([], []))
    assert result.status == "completed"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class FakeSkillsTable:
    def __init__(self, db: "FakeDb") -> None:
        self._db = db
        self._filter: str | None = None
        self.data: list[dict[str, Any]] = []

    def select(self, _columns: str) -> "FakeSkillsTable":
        self._filter = None
        return self

    def order(self, _column: str) -> "FakeSkillsTable":
        return self

    def eq(self, _column: str, value: str) -> "FakeSkillsTable":
        self._filter = value
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str) -> "FakeSkillsTable":
        assert on_conflict == "id"
        if self._db.fail_upsert:
            raise RuntimeError("db_down")
        self._db.skills[row["id"]] = dict(row)
        return self

    def execute(self) -> "FakeSkillsTable":
        rows = sorted(self._db.skills.values(), key=lambda r: r["id"])
        if self._filter is not None:
            rows = [r for r in rows if r["id"] == self._filter]
        self.data = rows
        return self


class FakeDb:
    def __init__(self) -> None:
        self.skills: dict[str, dict[str, Any]] = {}
        self.fail_upsert = False

    def table(self, name: str) -> FakeSkillsTable:
        assert name == "skills"
        return FakeSkillsTable(self)


class FakeAdminSheet:
    """In-memory stand-in for AdminGspreadSheet with the same award row logic."""

    def __init__(self, data: list[list[str]] | None = None) -> None:
        self.grid: list[list[str]] = [
            ["BTU | TEST DATA"],
            [""],
            [""],
            list(HEADER),
            *(data or []),
        ]
        self.tab: list[CatalogSkill] | None = None
        self.unavailable = False
        self.writebacks: list[list[RowOutcome]] = []

    def _check(self) -> None:
        if self.unavailable:
            raise SheetUnavailableError("sheet_unavailable")

    def ensure_skills_tab(self, seed: list[CatalogSkill]) -> list[CatalogSkill]:
        self._check()
        if self.tab is None:
            self.tab = list(seed)
        return list(self.tab)

    def append_skill(self, skill: CatalogSkill) -> None:
        self._check()
        assert self.tab is not None
        self.tab.append(skill)

    def update_skill(self, skill: CatalogSkill) -> bool:
        self._check()
        assert self.tab is not None
        for index, current in enumerate(self.tab):
            if current.id == skill.id:
                self.tab[index] = skill
                return True
        return False

    def append_awards(
        self, awards: list[AwardInput], known_emails: set[str]
    ) -> list[AwardPlacement]:
        self._check()
        header_index = find_header_row([list(r) for r in self.grid])
        assert header_index is not None
        rows, placements = build_award_rows(
            self.grid[header_index],
            [list(r) for r in self.grid[header_index + 1 :]],
            awards,
            known_emails,
            first_row=len(self.grid) + 1,
        )
        self.grid.extend(rows)
        return placements

    def read_rows(self) -> list[dict[str, object]]:
        self._check()
        return records_from_values([list(r) for r in self.grid])[1]

    def read_catalog(self) -> list[CatalogSkill]:
        return list(self.tab or [])

    def write_back(self, outcomes: list[RowOutcome]) -> None:
        self.writebacks.append(list(outcomes))

    def data_index(self, row_number: int) -> int:
        header_index = find_header_row([list(r) for r in self.grid])
        assert header_index is not None
        return row_number - (header_index + 2)


@pytest.fixture
def env(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[FakeDb, FakeAdminSheet, MemorySyncStore]]:
    db = FakeDb()
    sheet = FakeAdminSheet([existing_row()])
    store = MemorySyncStore()
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    monkeypatch.setattr(admin_mod, "get_supabase", lambda: db)
    app.dependency_overrides[get_admin_sheet] = lambda: sheet
    app.dependency_overrides[get_sync_store] = lambda: store
    yield db, sheet, store
    app.dependency_overrides.clear()


def seed_skill(db: FakeDb, skill_id: str = "SKL-002", name: str = "Prompting") -> None:
    db.skills[skill_id] = {
        "id": skill_id,
        "name": name,
        "name_ka": "",
        "category": "AI Skill",
        "badge": "BDG-AI-001",
        "description": "Writing prompts.",
    }


def test_skills_endpoints_require_admin() -> None:
    skill = {"name": "X", "category": "AI Skill"}
    award_body = {"skill_id": "SKL-001", "students": [{"email": "a@btu.edu.ge"}]}
    assert client.get("/admin/skills").status_code == 401
    assert client.post("/admin/skills", json=skill).status_code == 401
    assert client.patch("/admin/skills/SKL-001", json={}).status_code == 401
    assert client.post("/admin/awards", json=award_body).status_code == 401


def test_list_skills(env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore]) -> None:
    db, _, _ = env
    seed_skill(db)
    body = client.get("/admin/skills", headers=AUTH).json()
    assert body["skills"] == [
        {
            "id": "SKL-002",
            "name": "Prompting",
            "name_ka": "",
            "category": "AI Skill",
            "badge": "BDG-AI-001",
            "description": "Writing prompts.",
        }
    ]


def test_create_skill_writes_sheet_first_then_db(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, _ = env
    seed_skill(db, "SKL-016", "MLOps")
    response = client.post(
        "/admin/skills",
        headers=AUTH,
        json={
            "name": "  Data Storytelling ",
            "name_ka": "მონაცემები",
            "category": "AI Applied Skill",
            "description": "Explain data.",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "SKL-017"
    assert body["name"] == "Data Storytelling"
    assert body["badge"] == "BDG-AI-002"
    assert sheet.tab is not None
    assert [s.id for s in sheet.tab] == ["SKL-016", "SKL-017"]
    assert db.skills["SKL-017"]["name_ka"] == "მონაცემები"


def test_create_skill_rejects_duplicate_name(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, _ = env
    seed_skill(db, "SKL-002", "Prompting")
    response = client.post(
        "/admin/skills", headers=AUTH, json={"name": " prompting ", "category": "AI Skill"}
    )
    assert response.status_code == 409
    assert response.json() == {"code": "skill_name_taken"}
    assert sheet.tab is None


def test_create_skill_validates_input(env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore]) -> None:
    for payload in (
        {"name": "   ", "category": "AI Skill"},
        {"name": "X", "category": "Expert"},
        {"name": "X", "category": "AI Skill", "extra": 1},
    ):
        assert client.post("/admin/skills", headers=AUTH, json=payload).status_code == 422


def test_create_skill_finishes_a_half_saved_skill(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, _ = env
    sheet.tab = [CatalogSkill("SKL-001", "Half saved", "AI Skill", "BDG-AI-001", "", name_ka="")]
    response = client.post(
        "/admin/skills", headers=AUTH, json={"name": "Half saved", "category": "AI Skill"}
    )
    assert response.status_code == 201
    assert response.json()["id"] == "SKL-001"
    assert "SKL-001" in db.skills
    assert len(sheet.tab) == 1


def test_sheet_failure_returns_503_and_writes_no_db_row(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, _ = env
    sheet.unavailable = True
    response = client.post(
        "/admin/skills", headers=AUTH, json={"name": "New one", "category": "AI Skill"}
    )
    assert response.status_code == 503
    assert response.json() == {"code": "sheet_unavailable"}
    assert db.skills == {}


def test_update_skill_updates_sheet_and_db(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, _ = env
    seed_skill(db)
    response = client.patch(
        "/admin/skills/skl-002",
        headers=AUTH,
        json={"name_ka": "ინჟინერია", "category": "AI Advanced Skill"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Prompting"
    assert body["name_ka"] == "ინჟინერია"
    assert body["badge"] == "BDG-AI-003"
    assert sheet.tab is not None
    assert sheet.tab[0].category == "AI Advanced Skill"
    assert db.skills["SKL-002"]["badge"] == "BDG-AI-003"


def test_update_skill_errors(env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore]) -> None:
    db, _, _ = env
    seed_skill(db, "SKL-001", "One")
    seed_skill(db, "SKL-002", "Two")
    missing = client.patch("/admin/skills/SKL-099", headers=AUTH, json={"name": "X"})
    assert missing.status_code == 404
    assert missing.json() == {"code": "skill_not_found"}
    taken = client.patch("/admin/skills/SKL-002", headers=AUTH, json={"name": "one"})
    assert taken.status_code == 409
    assert taken.json() == {"code": "skill_name_taken"}


def test_award_appends_rows_then_syncs(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, store = env
    seed_skill(db)
    before = len(sheet.grid)
    response = client.post(
        "/admin/awards",
        headers=AUTH,
        json={
            "skill_id": "SKL-002",
            "awarded_on": "2026-10-28",
            "students": [
                {"email": "Nino@btu.edu.ge", "first_name": "Nino", "last_name": "Beridze"},
                {"email": "nino@btu.edu.ge"},
                {"email": "nobody@btu.edu.ge"},
                {"email": "bad@gmail.com", "first_name": "Bad"},
                {"email": "not-an-email"},
                {"email": "ada@btu.edu.ge"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    by_email = {row["email"]: row for row in body["rows"]}
    assert [row["email"] for row in body["rows"]] == [
        "nino@btu.edu.ge",
        "nobody@btu.edu.ge",
        "bad@gmail.com",
        "not-an-email",
        "ada@btu.edu.ge",
    ]
    assert by_email["nino@btu.edu.ge"]["status"] == "synced"
    assert by_email["nino@btu.edu.ge"]["version"] == "V1"
    assert by_email["nino@btu.edu.ge"]["passport_id"].startswith("BTU-")
    assert by_email["nobody@btu.edu.ge"] == {
        "email": "nobody@btu.edu.ge",
        "status": "failed",
        "error": "missing_full_name",
        "passport_id": "",
        "version": "",
    }
    assert by_email["bad@gmail.com"]["error"] == "email_domain_not_allowed"
    assert by_email["not-an-email"]["error"] == "invalid_email"
    # Ada already holds a different skill, so she gets a new row and a new version.
    assert by_email["ada@btu.edu.ge"]["status"] == "synced"
    assert body["sync_result"]["status"] == "completed"
    assert len(sheet.grid) == before + 2
    assert len(store.versions) == 2
    # Students reach the database only through the sync, which also links the skill.
    assert {s.email for s in store.students} == {"ada@btu.edu.ge", "nino@btu.edu.ge"}
    assert {"SKL-001", "SKL-002"} <= set(store.skills)


def test_award_reports_sync_failure_codes(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, store = env
    seed_skill(db)
    # A leftover row from another student already owns this passport id.
    sheet.grid.append(
        existing_row("other@btu.edu.ge", "SKL-005"),
    )
    other = sheet.grid[-1]
    other[HEADER.index("Passport ID (Existing)")] = "BTU-AI-000125"
    other[HEADER.index("Student ID")] = "BTU-T-0002"
    store.insert_student("ada@btu.edu.ge", "Ada Lovelace", "BTU-AI-000125")
    response = client.post(
        "/admin/awards",
        headers=AUTH,
        json={"skill_id": "SKL-002", "students": [{"email": "other@btu.edu.ge"}]},
    )
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["status"] == "failed"
    assert row["error"] == "passport_id_taken"


def test_award_skips_a_skill_the_student_already_has(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, _ = env
    seed_skill(db, "SKL-001", "AI Literacy")
    before = len(sheet.grid)
    response = client.post(
        "/admin/awards",
        headers=AUTH,
        json={"skill_id": "SKL-001", "students": [{"email": "ada@btu.edu.ge"}]},
    )
    body = response.json()
    assert body["rows"] == [
        {
            "email": "ada@btu.edu.ge",
            "status": "skipped",
            "error": "already_awarded",
            "passport_id": "",
            "version": "",
        }
    ]
    assert body["sync_result"]["status"] == "skipped"
    assert len(sheet.grid) == before


def test_award_row_is_pending_when_another_sync_is_running(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, sheet, store = env
    seed_skill(db)
    assert store.try_acquire()
    response = client.post(
        "/admin/awards",
        headers=AUTH,
        json={
            "skill_id": "SKL-002",
            "students": [{"email": "nino@btu.edu.ge", "first_name": "Nino"}],
        },
    )
    body = response.json()
    assert body["rows"][0]["status"] == "pending"
    assert body["sync_result"]["status"] == "skipped"
    assert body["sync_result"]["error"] == "sync_in_progress"
    assert sheet.grid[-1][HEADER.index("BTU Email (Test)")] == "nino@btu.edu.ge"


def test_award_unknown_skill_and_missing_level(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    db, _, _ = env
    unknown = client.post(
        "/admin/awards",
        headers=AUTH,
        json={"skill_id": "SKL-404", "students": [{"email": "a@btu.edu.ge"}]},
    )
    assert unknown.status_code == 404
    assert unknown.json() == {"code": "skill_not_found"}
    seed_skill(db)
    db.skills["SKL-002"]["category"] = ""
    nolevel = client.post(
        "/admin/awards",
        headers=AUTH,
        json={"skill_id": "SKL-002", "students": [{"email": "a@btu.edu.ge"}]},
    )
    assert nolevel.status_code == 422
    assert nolevel.json() == {"code": "award_level_required"}
    explicit = client.post(
        "/admin/awards",
        headers=AUTH,
        json={
            "skill_id": "SKL-002",
            "level": "AI Advanced Skill",
            "students": [{"email": "a@btu.edu.ge", "first_name": "A"}],
        },
    )
    assert explicit.status_code == 200
    assert explicit.json()["rows"][0]["status"] == "synced"


def test_award_sheet_unavailable(env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore]) -> None:
    db, sheet, _ = env
    seed_skill(db)
    sheet.unavailable = True
    response = client.post(
        "/admin/awards",
        headers=AUTH,
        json={"skill_id": "SKL-002", "students": [{"email": "a@btu.edu.ge", "first_name": "A"}]},
    )
    assert response.status_code == 503


def test_direct_student_creation_is_gone(
    env: tuple[FakeDb, FakeAdminSheet, MemorySyncStore],
) -> None:
    response = client.post(
        "/admin/students", headers=AUTH, json={"email": "x@btu.edu.ge", "full_name": "X"}
    )
    assert response.status_code == 405
