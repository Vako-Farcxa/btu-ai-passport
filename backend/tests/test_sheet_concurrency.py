"""Two admins writing at the same moment: every award gets its own row and its own IDs, and
two new skills never share an ID."""

import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_admin_skills import HEADER, FakeAdminSheet, FakeDb, existing_row

import passport_api.api.admin as admin_mod
import passport_api.sheet_admin as sheet_admin
from passport_api.api.admin import get_admin_sheet
from passport_api.main import app
from passport_api.sheet_admin import AdminGspreadSheet, AwardInput


class SlowWorksheet:
    """A worksheet whose reads take a moment, so two writers really overlap."""

    def __init__(self) -> None:
        self.grid: list[list[str]] = [list(HEADER), existing_row()]
        self.row_count = 1000

    def get_all_values(self) -> list[list[str]]:
        snapshot = [list(row) for row in self.grid]
        time.sleep(0.05)
        return snapshot

    def add_rows(self, count: int) -> None:
        self.row_count += count

    def update(self, rows: list[list[str]], cell: str, value_input_option: str = "") -> None:
        assert value_input_option == "RAW"
        start = int(cell[1:])
        for offset, row in enumerate(rows):
            index = start - 1 + offset
            while len(self.grid) <= index:
                self.grid.append([])
            self.grid[index] = list(row)


class Spreadsheet:
    def __init__(self, worksheet: SlowWorksheet) -> None:
        self._worksheet = worksheet

    def get_worksheet(self, _index: int) -> SlowWorksheet:
        return self._worksheet


def award(email: str, skill_id: str, name: str) -> AwardInput:
    return AwardInput(
        email=email,
        first_name="Nino",
        last_name="Beridze",
        skill_id=skill_id,
        skill_name=name,
        category="AI Skill",
        badge="BDG-AI-001",
        description="",
        awarded_on="2026-10-28",
    )


def run_together(jobs: list[Any]) -> None:
    barrier = threading.Barrier(len(jobs))
    errors: list[BaseException] = []

    def wrap(job: Any) -> None:
        barrier.wait()
        try:
            job()
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=wrap, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


def test_two_admins_awarding_at_once_get_different_rows_and_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worksheet = SlowWorksheet()
    monkeypatch.setattr(sheet_admin, "open_spreadsheet", lambda: Spreadsheet(worksheet))
    sheets = [AdminGspreadSheet(), AdminGspreadSheet()]
    placements: list[Any] = []
    lock = threading.Lock()

    def job(index: int, email: str) -> Any:
        def run() -> None:
            result = sheets[index].append_awards([award(email, "SKL-002", "Prompting")], set())
            with lock:
                placements.extend(result)

        return run

    run_together([job(0, "one@btu.edu.ge"), job(1, "two@btu.edu.ge")])

    assert sorted(p.row_number for p in placements if p.row_number) == [3, 4]
    data = [dict(zip(HEADER, row, strict=True)) for row in worksheet.grid[1:]]
    assert [row["BTU Email (Test)"] for row in data[1:]].count("one@btu.edu.ge") == 1
    assert {row["BTU Email (Test)"] for row in data} == {
        "ada@btu.edu.ge",
        "one@btu.edu.ge",
        "two@btu.edu.ge",
    }
    student_ids = [row["Student ID"] for row in data]
    record_ids = [row["Record ID"] for row in data]
    assert len(set(student_ids)) == len(student_ids) == 3
    assert len(set(record_ids)) == len(record_ids) == 3


def test_ten_admins_at_once_never_overwrite_each_other(monkeypatch: pytest.MonkeyPatch) -> None:
    worksheet = SlowWorksheet()
    monkeypatch.setattr(sheet_admin, "open_spreadsheet", lambda: Spreadsheet(worksheet))
    sheet = AdminGspreadSheet()
    emails = [f"person{letter}@btu.edu.ge" for letter in "abcdefghij"]
    run_together(
        [
            lambda email=email: sheet.append_awards([award(email, "SKL-002", "Prompting")], set())
            for email in emails
        ]
    )
    written = [row[HEADER.index("BTU Email (Test)")] for row in worksheet.grid[2:]]
    assert sorted(written) == sorted(emails)
    ids = [row[HEADER.index("Record ID")] for row in worksheet.grid[1:]]
    assert len(set(ids)) == len(ids) == 11


def test_two_skills_saved_at_once_get_different_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowTabSheet(FakeAdminSheet):
        def ensure_skills_tab(self, seed: Any) -> Any:
            tab = super().ensure_skills_tab(seed)
            time.sleep(0.05)
            return tab

    db, sheet = FakeDb(), SlowTabSheet([existing_row()])
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    monkeypatch.setattr(admin_mod, "get_supabase", lambda: db)
    app.dependency_overrides[get_admin_sheet] = lambda: sheet
    client = TestClient(app)
    codes: list[tuple[int, str]] = []
    lock = threading.Lock()

    def save(name: str) -> Any:
        def run() -> None:
            response = client.post(
                "/admin/skills",
                headers={"Authorization": "Bearer x"},
                json={"name": name, "category": "AI Skill"},
            )
            with lock:
                codes.append((response.status_code, response.json().get("id", "")))

        return run

    try:
        run_together([save("Data Ethics"), save("Model Evaluation"), save("Prompt Safety")])
    finally:
        app.dependency_overrides.clear()
    assert sorted(status for status, _ in codes) == [201, 201, 201]
    assert sorted(skill_id for _, skill_id in codes) == ["SKL-001", "SKL-002", "SKL-003"]
