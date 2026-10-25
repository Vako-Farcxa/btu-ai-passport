import re
from pathlib import Path

import openpyxl
import pytest

from passport_api.settings import email_domain_allowed, settings
from passport_api.sync import (
    FakeSheet,
    MemorySyncStore,
    find_header_row,
    records_from_values,
    run_sync,
    write_back_ranges,
)

FIXTURE = Path(__file__).parent / "fixtures" / "official_test_data.xlsx"
SYNCED_AT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$")


def _grid() -> list[list[object]]:
    workbook = openpyxl.load_workbook(FIXTURE)
    sheet = workbook.worksheets[0]
    return [
        ["" if cell is None else cell for cell in row] for row in sheet.iter_rows(values_only=True)
    ]


@pytest.fixture
def test_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "allowed_email_domains", "btu.edu.ge, example.org")


def _official() -> tuple[list[str], list[dict[str, object]]]:
    return records_from_values(_grid())


def _data_records(records: list[dict[str, object]]) -> list[tuple[int, dict[str, object]]]:
    return [(i, r) for i, r in enumerate(records) if str(r["BTU Email (Test)"]).strip()]


def test_header_is_found_below_title_rows() -> None:
    grid = _grid()
    index = find_header_row(grid)
    assert index == 3
    header, records = records_from_values(grid)
    assert header[3] == "BTU Email (Test)"
    assert header[16:] == [
        "Passport Sync Status",
        "Synced Passport Version",
        "Synced At (UTC)",
        "Sync Error / Notes",
    ]
    assert records[0]["Student ID"] == "BTU-T-0001"


def test_old_header_on_row_one_is_still_found() -> None:
    header, records = records_from_values(
        [["Email", "Full_Name", "Skill"], ["ada@btu.edu.ge", "Ada", "Python"]]
    )
    assert header == ["Email", "Full_Name", "Skill"]
    assert records == [{"Email": "ada@btu.edu.ge", "Full_Name": "Ada", "Skill": "Python"}]


@pytest.mark.usefixtures("test_domains")
def test_official_sheet_issues_passports_with_existing_ids() -> None:
    _, records = _official()
    data = _data_records(records)
    store = MemorySyncStore()
    sheet = FakeSheet([{k: str(v) for k, v in r.items()} for r in records])

    result = run_sync(store, sheet)

    emails = {str(r["BTU Email (Test)"]).lower() for _, r in data}
    assert result.status == "completed"
    assert result.versions_created == len(emails)
    assert {s.email for s in store.students} == emails
    expected_ids = {
        str(r["BTU Email (Test)"]).lower(): str(r["Passport ID (Existing)"]) for _, r in data
    }
    for student in store.students:
        assert student.passport_id == expected_ids[student.email]
    giorgi = next(s for s in store.students if s.email == "btu-t-0001@example.org")
    assert giorgi.full_name == "Giorgi Kapanadze"
    giorgi_version = next(v for v in store.versions if v.email == giorgi.email)
    assert {skill.badge for skill in giorgi_version.skills} <= {
        "BDG-AI-001",
        "BDG-AI-002",
        "BDG-AI-003",
    }
    assert "AI Literacy" in {skill.skill for skill in giorgi_version.skills}

    (written,) = sheet.writes
    assert [o.index for o in written] == [i for i, _ in data]
    for outcome in written:
        assert outcome.status == "SYNCED"
        assert outcome.version == "V1"
        assert SYNCED_AT.match(outcome.synced_at)
        assert outcome.error == ""
        assert outcome.passport_id == expected_ids[str(records[outcome.index]["BTU Email (Test)"])]


@pytest.mark.usefixtures("test_domains")
def test_new_official_row_creates_v2_and_keeps_passport_id() -> None:
    _, records = _official()
    rows = [{k: str(v) for k, v in r.items()} for _, r in _data_records(records)]
    store = MemorySyncStore()
    run_sync(store, FakeSheet(rows))
    added = dict(rows[0])
    added.update(
        {
            "Record ID": "REC-9999",
            "Skill ID": "SKL-099",
            "Skill Name": "Agentic AI Systems",
            "Skill Category": "AI Advanced Skill",
            "Date Earned": "2026-10-24",
            "Passport Sync Status": "NOT SYNCED",
        }
    )
    sheet = FakeSheet([*rows, added])

    result = run_sync(store, sheet)

    assert result.versions_created == 1
    all_rows = [*rows, added]
    student_rows = [
        o
        for o in sheet.writes[0]
        if all_rows[o.index]["BTU Email (Test)"] == added["BTU Email (Test)"]
    ]
    assert {o.version for o in student_rows} == {"V2"}
    assert {o.passport_id for o in student_rows} == {"BTU-AI-000125"}
    latest = max(
        (v for v in store.versions if v.email == "btu-t-0001@example.org"),
        key=lambda v: v.version_number,
    )
    assert ("Agentic AI Systems", "BDG-AI-003") in {(s.skill, s.badge) for s in latest.skills}


def test_example_org_rows_fail_when_domain_not_allowed() -> None:
    _, records = _official()
    rows = [{k: str(v) for k, v in r.items()} for _, r in _data_records(records)][:2]
    store = MemorySyncStore()
    sheet = FakeSheet(rows)

    result = run_sync(store, sheet)

    assert result.versions_created == 0
    assert store.students == []
    assert [(o.status, o.error) for o in sheet.writes[0]] == [
        ("FAILED", "email_domain_not_allowed"),
        ("FAILED", "email_domain_not_allowed"),
    ]


@pytest.mark.usefixtures("test_domains")
def test_taken_existing_passport_id_fails_the_rows() -> None:
    _, records = _official()
    first = {k: str(v) for k, v in records[0].items()}
    other = dict(first, **{"BTU Email (Test)": "someone@example.org", "Student ID": "X"})
    store = MemorySyncStore()
    run_sync(store, FakeSheet([first]))
    sheet = FakeSheet([first, other])

    run_sync(store, sheet)

    by_index = {o.index: o for o in sheet.writes[0]}
    assert by_index[0].status == "SYNCED"
    assert (by_index[1].status, by_index[1].error) == ("FAILED", "passport_id_taken")


def test_blank_and_note_rows_are_not_written_and_missing_skill_is_failed() -> None:
    sheet = FakeSheet(
        [
            {"email": "", "skill": ""},
            {"email": "ada@btu.edu.ge", "full_name": "Ada", "skill": ""},
            {"email": "", "full_name": "TECHNICAL NOTES", "skill": ""},
        ]
    )
    run_sync(MemorySyncStore(), sheet)
    assert [(o.index, o.status, o.error) for o in sheet.writes[0]] == [
        (1, "FAILED", "missing_skill")
    ]


def test_write_back_targets_official_output_columns() -> None:
    header, records = _official()
    from passport_api.sync import RowOutcome

    updates = write_back_ranges(
        header,
        5,
        [RowOutcome(0, "SYNCED", "V2", "2026-10-25 15:00 UTC", "", "BTU-AI-000125")],
    )
    assert updates == [
        {"range": "Q5", "values": [["SYNCED"]]},
        {"range": "R5", "values": [["V2"]]},
        {"range": "S5", "values": [["2026-10-25 15:00 UTC"]]},
        {"range": "T5", "values": [[""]]},
        {"range": "G5", "values": [["BTU-AI-000125"]]},
    ]
    assert records


def test_write_back_skips_columns_the_old_sheet_does_not_have() -> None:
    from passport_api.sync import RowOutcome

    updates = write_back_ranges(
        ["email", "full_name", "skill"], 2, [RowOutcome(0, "SYNCED", "V1", "x", "", "BTU-X")]
    )
    assert updates == []


def test_allowed_domains_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert email_domain_allowed("Ada@BTU.edu.ge")
    assert not email_domain_allowed("ada@example.org")
    assert not email_domain_allowed("ada@evilbtu.edu.ge")
    monkeypatch.setattr(settings, "allowed_email_domains", "btu.edu.ge,@example.org")
    assert email_domain_allowed("btu-t-0001@example.org")
