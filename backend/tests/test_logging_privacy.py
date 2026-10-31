"""What the sync writes to the logs: error types and codes, never an email address or the text of
a database error (a Postgres unique violation quotes the values that clashed)."""

import logging

import pytest
from postgrest.exceptions import APIError

from passport_api.sync import FakeSheet, MemorySyncStore, StudentUnit, UnitResult, run_sync

EMAIL = "ada.lovelace@btu.edu.ge"
ROW = {
    "email": EMAIL,
    "full_name": "Ada Lovelace",
    "skill": "Python",
    "badge": "",
    "awarded_on": "2026-09-18",
}
CLASH = APIError(
    {
        "code": "23505",
        "message": 'duplicate key value violates unique constraint "students_email_key"',
        "details": f"Key (email)=({EMAIL}) already exists.",
    }
)


class ClashingStore(MemorySyncStore):
    def commit_student_unit(self, unit: StudentUnit) -> UnitResult:
        raise CLASH


def test_a_database_error_on_one_student_is_logged_without_their_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sheet = FakeSheet([ROW])
    with caplog.at_level(logging.DEBUG):
        run_sync(ClashingStore(), sheet)
    assert [(o.status, o.error) for o in sheet.writes[0]] == [("FAILED", "student_conflict")]
    assert "student_sync_failed" in caplog.text
    assert "sqlstate=23505" in caplog.text
    assert EMAIL not in caplog.text
    assert "ada.lovelace" not in caplog.text
    assert "already exists" not in caplog.text
    assert "students_email_key" not in caplog.text


def test_the_same_student_always_gets_the_same_log_tag(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        run_sync(ClashingStore(), FakeSheet([ROW]))
        run_sync(ClashingStore(), FakeSheet([ROW]))
    tags = {
        part.split("=", 1)[1]
        for record in caplog.records
        for part in record.getMessage().split()
        if part.startswith("student=")
    }
    assert len(tags) == 1
    assert len(next(iter(tags))) == 8


def test_an_unreadable_sheet_is_logged_through_logging_without_the_error_text(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = FakeSheet(error=RuntimeError("https://sheets.example/spreadsheets/d/SECRET-SHEET-ID"))
    with caplog.at_level(logging.WARNING):
        result = run_sync(MemorySyncStore(), sheet)
    assert result.error == "sheet_unavailable"
    assert "sheet_read_failed: RuntimeError" in caplog.text
    assert "SECRET-SHEET-ID" not in caplog.text
    assert capsys.readouterr().out == ""  # nothing is printed any more


def test_a_crash_inside_the_run_is_logged_by_type_only(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import passport_api.sync as sync_mod

    def explode(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError(f"cannot write {EMAIL}")

    monkeypatch.setattr(sync_mod, "_issue_versions", explode)
    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        run_sync(MemorySyncStore(), FakeSheet([ROW]))
    assert "sync_failed: RuntimeError" in caplog.text
    assert EMAIL not in caplog.text
