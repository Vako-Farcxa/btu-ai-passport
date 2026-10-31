"""The Google Sheets adapters, against a fake spreadsheet that behaves like gspread: opening the
spreadsheet from settings, the Skills tab, and failures that must surface as one error."""

import json
from typing import Any

import gspread
import pytest

import passport_api.sheet_admin as sheet_admin
from passport_api.settings import settings
from passport_api.sheet_admin import AdminGspreadSheet
from passport_api.sync import (
    SKILLS_HEADER,
    SKILLS_TAB,
    CatalogSkill,
    SheetUnavailableError,
    open_spreadsheet,
)


class Worksheet:
    def __init__(self, title: str, values: list[list[str]]) -> None:
        self.title = title
        self.values = values
        self.updates: list[tuple[list[list[str]], str, str]] = []
        self.fail_updates = False
        self.fail_reads = False

    def get_all_values(self) -> list[list[str]]:
        if self.fail_reads:
            raise RuntimeError("quota")
        return [list(row) for row in self.values]

    def update(self, rows: list[list[str]], cell: str, value_input_option: str = "") -> None:
        if self.fail_updates:
            raise RuntimeError("quota")
        self.updates.append((rows, cell, value_input_option))


class Spreadsheet:
    def __init__(self, tabs: list[Worksheet]) -> None:
        self.tabs = tabs
        self.added: list[Worksheet] = []
        self.fail_add = False

    def worksheet(self, title: str) -> Worksheet:
        for tab in self.tabs:
            if tab.title == title:
                return tab
        raise gspread.WorksheetNotFound(title)

    def add_worksheet(self, title: str, rows: int, cols: int) -> Worksheet:
        if self.fail_add:
            raise RuntimeError("no permission")
        assert rows >= 100 and cols == len(SKILLS_HEADER)
        tab = Worksheet(title, [])
        self.tabs.append(tab)
        self.added.append(tab)
        return tab


def skill(skill_id: str = "SKL-001", name: str = "AI Literacy") -> CatalogSkill:
    return CatalogSkill(skill_id, name, "AI Skill", "BDG-AI-001", "Basics.", name_ka="ეთიკა")


def use(monkeypatch: pytest.MonkeyPatch, spreadsheet: Spreadsheet) -> AdminGspreadSheet:
    monkeypatch.setattr(sheet_admin, "open_spreadsheet", lambda: spreadsheet)
    return AdminGspreadSheet()


# -- open_spreadsheet ------------------------------------------------------------------


def test_opening_needs_a_sheet_id_and_credentials() -> None:
    with pytest.raises(SheetUnavailableError, match="sheet_not_configured"):
        open_spreadsheet()


@pytest.mark.parametrize("credentials", ["not json", "[]", '"text"', "123"])
def test_unusable_credentials_are_reported_as_not_configured(
    monkeypatch: pytest.MonkeyPatch, credentials: str
) -> None:
    monkeypatch.setattr(settings, "sheet_id", "sheet-1")
    monkeypatch.setattr(settings, "google_service_account_json", credentials)
    with pytest.raises(SheetUnavailableError, match="sheet_not_configured"):
        open_spreadsheet()


def test_escaped_newlines_in_the_private_key_are_repaired_and_the_timeout_is_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class Client:
        def set_timeout(self, seconds: float) -> None:
            seen["timeout"] = seconds

        def open_by_key(self, key: str) -> str:
            seen["key"] = key
            return "the-spreadsheet"

    def service_account(info: dict[str, Any], scopes: list[str]) -> Client:
        seen["info"], seen["scopes"] = info, scopes
        return Client()

    monkeypatch.setattr(settings, "sheet_id", "sheet-1")
    monkeypatch.setattr(
        settings,
        "google_service_account_json",
        json.dumps({"private_key": "line1\\nline2", "client_email": "x@y"}),
    )
    monkeypatch.setattr(gspread, "service_account_from_dict", service_account)
    result = open_spreadsheet(timeout=4.0, scopes=["scope-a"])
    assert result == "the-spreadsheet"
    assert seen["info"]["private_key"] == "line1\nline2"
    assert (seen["scopes"], seen["timeout"], seen["key"]) == (["scope-a"], 4.0, "sheet-1")


def test_a_google_failure_while_opening_is_one_sheet_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("401 SECRET-DETAIL")

    monkeypatch.setattr(settings, "sheet_id", "sheet-1")
    monkeypatch.setattr(settings, "google_service_account_json", json.dumps({"a": 1}))
    monkeypatch.setattr(gspread, "service_account_from_dict", refuse)
    with pytest.raises(SheetUnavailableError) as caught:
        open_spreadsheet()
    assert "SECRET-DETAIL" not in str(caught.value)


# -- the Skills tab --------------------------------------------------------------------


def test_a_missing_skills_tab_is_created_and_seeded_with_the_database_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spreadsheet = Spreadsheet([Worksheet("Passports", [])])
    sheet = use(monkeypatch, spreadsheet)
    # The fake keeps what was written, as Google would, so the read after the write sees it.
    original = Worksheet.update

    def update(
        self: Worksheet, rows: list[list[str]], cell: str, value_input_option: str = ""
    ) -> None:
        original(self, rows, cell, value_input_option)
        self.values = rows

    monkeypatch.setattr(Worksheet, "update", update)
    tab = sheet.ensure_skills_tab([skill()])
    assert [s.id for s in tab] == ["SKL-001"]
    (created,) = spreadsheet.added
    assert created.title == SKILLS_TAB
    assert created.updates[0][0][0] == list(SKILLS_HEADER)
    assert created.updates[0][1:] == ("A1", "RAW")


def test_an_existing_skills_tab_is_read_not_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    tab = Worksheet(SKILLS_TAB, [list(SKILLS_HEADER), ["SKL-009", "Prompting", "", "AI Skill", ""]])
    spreadsheet = Spreadsheet([tab])
    result = use(monkeypatch, spreadsheet).ensure_skills_tab([skill()])
    assert [s.id for s in result] == ["SKL-009"]
    assert tab.updates == [] and spreadsheet.added == []


def test_an_empty_skills_tab_gets_its_header(monkeypatch: pytest.MonkeyPatch) -> None:
    tab = Worksheet(SKILLS_TAB, [[""], []])
    result = use(monkeypatch, Spreadsheet([tab])).ensure_skills_tab([])
    assert result == []
    assert tab.updates == [([list(SKILLS_HEADER)], "A1", "RAW")]


def test_a_failure_creating_the_tab_is_one_sheet_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spreadsheet = Spreadsheet([])
    spreadsheet.fail_add = True
    with pytest.raises(SheetUnavailableError):
        use(monkeypatch, spreadsheet).ensure_skills_tab([])


def test_a_skill_is_appended_below_the_last_row(monkeypatch: pytest.MonkeyPatch) -> None:
    tab = Worksheet(SKILLS_TAB, [list(SKILLS_HEADER), ["SKL-001", "One", "", "AI Skill", ""]])
    sheet = use(monkeypatch, Spreadsheet([tab]))
    sheet.ensure_skills_tab([])
    sheet.append_skill(skill("SKL-002", "Two"))
    rows, cell, mode = tab.updates[-1]
    assert (cell, mode) == ("A3", "RAW")
    assert rows == [["SKL-002", "Two", "ეთიკა", "AI Skill", "Basics."]]


def test_a_skill_is_updated_in_place_and_an_unknown_one_reports_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = Worksheet(
        SKILLS_TAB,
        [
            list(SKILLS_HEADER),
            ["SKL-001", "One", "", "AI Skill", ""],
            ["SKL-002", "Two", "", "AI Skill", ""],
        ],
    )
    sheet = use(monkeypatch, Spreadsheet([tab]))
    sheet.ensure_skills_tab([])
    assert sheet.update_skill(skill("SKL-002", "Two renamed")) is True
    assert tab.updates[-1][1] == "A3"
    assert tab.updates[-1][0][0][1] == "Two renamed"
    assert sheet.update_skill(skill("SKL-404", "Nobody")) is False


def test_writing_a_skill_before_the_tab_is_loaded_is_refused() -> None:
    sheet = AdminGspreadSheet()
    with pytest.raises(SheetUnavailableError):
        sheet.append_skill(skill())
    with pytest.raises(SheetUnavailableError):
        sheet.update_skill(skill())


def test_a_tab_without_a_skill_id_column_is_not_written_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = Worksheet(SKILLS_TAB, [["something", "else"], ["x", "y"]])
    sheet = use(monkeypatch, Spreadsheet([tab]))
    sheet.ensure_skills_tab([])
    with pytest.raises(SheetUnavailableError):
        sheet.append_skill(skill())
    assert tab.updates == []


def test_write_failures_on_the_tab_are_one_sheet_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = Worksheet(SKILLS_TAB, [list(SKILLS_HEADER), ["SKL-001", "One", "", "AI Skill", ""]])
    sheet = use(monkeypatch, Spreadsheet([tab]))
    sheet.ensure_skills_tab([])
    tab.fail_updates = True
    with pytest.raises(SheetUnavailableError):
        sheet.append_skill(skill("SKL-002", "Two"))
    with pytest.raises(SheetUnavailableError):
        sheet.update_skill(skill("SKL-001", "One again"))


# -- awards: reading and writing failures ------------------------------------------------


def test_award_reads_that_fail_are_one_sheet_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from passport_api.sheet_admin import AwardInput

    main = Worksheet("Passports", [])
    main.fail_reads = True

    class Book(Spreadsheet):
        def get_worksheet(self, _index: int) -> Worksheet:
            return main

    sheet = use(monkeypatch, Book([main]))
    award = AwardInput(
        "a@btu.edu.ge", "A", "B", "SKL-1", "Skill", "AI Skill", "BDG", "", "2026-10-28"
    )
    with pytest.raises(SheetUnavailableError):
        sheet.append_awards([award], set())


def test_a_sheet_without_a_header_row_is_unavailable_for_awards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from passport_api.sheet_admin import AwardInput

    main = Worksheet("Passports", [["just", "notes"]])

    class Book(Spreadsheet):
        def get_worksheet(self, _index: int) -> Worksheet:
            return main

    sheet = use(monkeypatch, Book([main]))
    award = AwardInput(
        "a@btu.edu.ge", "A", "B", "SKL-1", "Skill", "AI Skill", "BDG", "", "2026-10-28"
    )
    with pytest.raises(SheetUnavailableError):
        sheet.append_awards([award], set())
