"""Admin writes to the Google Sheet: the Skills tab and award rows.

The sheet stays the source of truth. Awards are appended to the main worksheet in the
same layout the sync reads, and the sync then copies them into the database.
"""

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import gspread

from passport_api.sync import (
    _ALIASES,
    SKILLS_HEADER,
    SKILLS_TAB,
    CatalogSkill,
    GspreadSheet,
    Sheet,
    SheetUnavailableError,
    _cell,
    catalog_from_values,
    find_header_row,
    open_spreadsheet,
)

_log = logging.getLogger(__name__)
_RECORD_ID = re.compile(r"^REC-(\d+)$", re.IGNORECASE)
# Student IDs in the sheet look like BTU-T-0042. A new one is the highest number + 1.
_STUDENT_ID = re.compile(r"^BTU-T-(\d+)$", re.IGNORECASE)
_STUDENT_ID_WIDTH = 4
# Columns copied from a student's earlier row so one student looks the same on every row.
_STUDENT_COLUMNS = (
    "student id",
    "program",
    "education level",
    "passport id (existing)",
    "first issued (existing)",
    "student status",
)
_RECORD_ID_COLUMNS = ("record id",)
_STATUS_COLUMNS = ("student status",)


def next_student_id(taken: Iterable[str]) -> str:
    """The next unused BTU-T-#### number, above every student ID already in use."""
    numbers = [
        int(match.group(1)) for value in taken if (match := _STUDENT_ID.match(value.strip()))
    ]
    return f"BTU-T-{max(numbers, default=0) + 1:0{_STUDENT_ID_WIDTH}d}"


ALREADY_AWARDED = "already_awarded"
MISSING_FULL_NAME = "missing_full_name"


@dataclass(frozen=True)
class AwardInput:
    email: str
    first_name: str
    last_name: str
    skill_id: str
    skill_name: str
    category: str
    badge: str
    description: str
    awarded_on: str
    # Used only when the student has no row in the sheet yet.
    program: str = ""
    education_level: str = ""
    # The passport the database already holds for this email, if any. Written into the new
    # row so the sheet matches the database. Never minted here: the sync mints new ones.
    passport_id: str = ""


@dataclass(frozen=True)
class AwardPlacement:
    """Where one award landed. row_number is the 1-based sheet row, or None if not written."""

    email: str
    row_number: int | None
    error: str


class AdminSheet(Sheet, Protocol):
    def ensure_skills_tab(self, seed: list[CatalogSkill]) -> list[CatalogSkill]: ...

    def append_skill(self, skill: CatalogSkill) -> None: ...

    def update_skill(self, skill: CatalogSkill) -> bool: ...

    def append_awards(
        self, awards: list[AwardInput], known_emails: set[str]
    ) -> list[AwardPlacement]: ...

    def data_index(self, row_number: int) -> int: ...


class AdminGspreadSheet(GspreadSheet):
    def __init__(self) -> None:
        super().__init__()
        self._skills_sheet: Any = None

    # -- Skills tab ---------------------------------------------------------

    def ensure_skills_tab(self, seed: list[CatalogSkill]) -> list[CatalogSkill]:
        """Skills in the tab. A missing tab is created and filled from `seed`."""
        spreadsheet = open_spreadsheet()
        try:
            try:
                worksheet = spreadsheet.worksheet(SKILLS_TAB)
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=SKILLS_TAB, rows=max(200, len(seed) + 100), cols=len(SKILLS_HEADER)
                )
                rows = [list(SKILLS_HEADER)] + [_tab_row(list(SKILLS_HEADER), s) for s in seed]
                worksheet.update(rows, "A1", value_input_option="RAW")
            values = cast(list[list[object]], worksheet.get_all_values())
            if not any(any(_cell(cell) for cell in row) for row in values):
                worksheet.update([list(SKILLS_HEADER)], "A1", value_input_option="RAW")
                values = [list(SKILLS_HEADER)]
        except SheetUnavailableError:
            raise
        except Exception as exc:
            _log.warning("skills_tab_failed: %s", type(exc).__name__, exc_info=True)
            raise SheetUnavailableError("sheet_unavailable") from exc
        self._skills_sheet = worksheet
        return catalog_from_values(values)

    def append_skill(self, skill: CatalogSkill) -> None:
        worksheet = self._require_skills_sheet()
        values = cast(list[list[object]], worksheet.get_all_values())
        header = _tab_header(values)
        next_row = len(values) + 1
        try:
            worksheet.update([_tab_row(header, skill)], f"A{next_row}", value_input_option="RAW")
        except Exception as exc:
            _log.warning("skills_tab_failed: %s", type(exc).__name__, exc_info=True)
            raise SheetUnavailableError("sheet_unavailable") from exc

    def update_skill(self, skill: CatalogSkill) -> bool:
        worksheet = self._require_skills_sheet()
        values = cast(list[list[object]], worksheet.get_all_values())
        header = _tab_header(values)
        id_position = header.index("skill_id")
        for index, row in enumerate(values):
            if index == 0 or id_position >= len(row):
                continue
            if _cell(row[id_position]).upper() == skill.id:
                try:
                    worksheet.update(
                        [_tab_row(header, skill)], f"A{index + 1}", value_input_option="RAW"
                    )
                except Exception as exc:
                    _log.warning("skills_tab_failed: %s", type(exc).__name__, exc_info=True)
                    raise SheetUnavailableError("sheet_unavailable") from exc
                return True
        return False

    def _require_skills_sheet(self) -> Any:
        if self._skills_sheet is None:
            raise SheetUnavailableError("sheet_unavailable")
        return self._skills_sheet

    # -- Awards -------------------------------------------------------------

    def append_awards(
        self, awards: list[AwardInput], known_emails: set[str]
    ) -> list[AwardPlacement]:
        """Append one row per award to the main worksheet, in the layout the sync reads."""
        spreadsheet = open_spreadsheet()
        try:
            worksheet = spreadsheet.get_worksheet(0)
            values = cast(list[list[object]], worksheet.get_all_values())
        except Exception as exc:
            _log.warning("sheet_read_failed: %s", type(exc).__name__, exc_info=True)
            raise SheetUnavailableError("sheet_unavailable") from exc
        header_index = find_header_row(values)
        if header_index is None:
            raise SheetUnavailableError("sheet_unavailable")
        header = [_cell(cell) for cell in values[header_index]]
        rows, placements = build_award_rows(
            header, values[header_index + 1 :], awards, known_emails, first_row=len(values) + 1
        )
        if rows:
            first_row = len(values) + 1
            try:
                needed = first_row + len(rows) - 1
                if needed > worksheet.row_count:
                    worksheet.add_rows(needed - worksheet.row_count)
                worksheet.update(rows, f"A{first_row}", value_input_option="RAW")
            except Exception as exc:
                _log.warning("award_write_failed: %s", type(exc).__name__, exc_info=True)
                raise SheetUnavailableError("sheet_unavailable") from exc
        return placements

    def data_index(self, row_number: int) -> int:
        """Index of a sheet row in read_rows(). Valid after read_rows() has run."""
        return row_number - self._first_data_row


def _tab_header(values: list[list[object]]) -> list[str]:
    header = [_cell(cell).lower() for cell in values[0]] if values else []
    if "skill_id" not in header:
        raise SheetUnavailableError("sheet_unavailable")
    return header


def _tab_row(header: list[str], skill: CatalogSkill) -> list[str]:
    by_name = {
        "skill_id": skill.id,
        "name_en": skill.name,
        "name_ka": skill.name_ka or "",
        "category": skill.category,
        "description": skill.description,
    }
    return [by_name.get(name, "") for name in header]


def _column(header: list[str], names: tuple[str, ...]) -> int | None:
    lowered = [name.strip().lower() for name in header]
    for position, name in enumerate(lowered):
        if name in names:
            return position
    return None


def build_award_rows(
    header: list[str],
    data: Sequence[Sequence[object]],
    awards: list[AwardInput],
    known_emails: set[str],
    *,
    first_row: int,
) -> tuple[list[list[str]], list[AwardPlacement]]:
    """New sheet rows for `awards` plus where each one lands. Pure, so it is easy to test."""
    columns = {field: _column(header, names) for field, names in _ALIASES.items()}
    record_column = _column(header, _RECORD_ID_COLUMNS)
    email_column = columns["email"]
    if email_column is None:
        raise SheetUnavailableError("sheet_unavailable")

    def cell_at(row: Sequence[object], position: int | None) -> str:
        return _cell(row[position]) if position is not None and position < len(row) else ""

    earlier: dict[str, Sequence[object]] = {}
    awarded: set[tuple[str, str]] = set()
    highest_record = 0
    # What each student already has in the sheet, taken from any of their rows.
    own_student_id: dict[str, str] = {}
    own_passport_id: dict[str, str] = {}
    used_student_ids: set[str] = set()
    student_id_column = _column(header, ("student id",))
    passport_column = _column(header, ("passport id (existing)",))
    for old in data:
        email = cell_at(old, email_column).lower()
        existing_student_id = cell_at(old, student_id_column)
        if existing_student_id:
            used_student_ids.add(existing_student_id)
        if email:
            earlier[email] = old
            if existing_student_id:
                own_student_id[email] = existing_student_id
            if cell_at(old, passport_column):
                own_passport_id[email] = cell_at(old, passport_column)
            awarded.add((email, cell_at(old, columns["skill_id"]).upper()))
            awarded.add((email, cell_at(old, columns["skill"]).lower()))
        match = _RECORD_ID.match(cell_at(old, record_column))
        if match:
            highest_record = max(highest_record, int(match.group(1)))

    rows: list[list[str]] = []
    placements: list[AwardPlacement] = []
    for award in awards:
        email = award.email.lower()
        if (email, award.skill_id.upper()) in awarded or (
            email,
            award.skill_name.lower(),
        ) in awarded:
            placements.append(AwardPlacement(email, None, ALREADY_AWARDED))
            continue
        template = earlier.get(email)
        first_name, last_name = award.first_name.strip(), award.last_name.strip()
        if template is None and email not in known_emails and not (first_name or last_name):
            placements.append(AwardPlacement(email, None, MISSING_FULL_NAME))
            continue
        row = [""] * len(header)
        values: dict[str, str] = {}
        if template is not None:
            for position, name in enumerate(header):
                if name.strip().lower() in _STUDENT_COLUMNS and position < len(template):
                    row[position] = _cell(template[position])
            for field in ("first_name", "last_name", "full_name"):
                values[field] = cell_at(template, columns[field])
        else:
            values.update(
                first_name=first_name,
                last_name=last_name,
                full_name=f"{first_name} {last_name}".strip(),
            )
            status_column = _column(header, _STATUS_COLUMNS)
            if status_column is not None:
                row[status_column] = "Active"
            for names, text in (
                (("program",), award.program.strip()),
                (("education level",), award.education_level.strip()),
            ):
                text_column = _column(header, names)
                if text_column is not None:
                    row[text_column] = text
        # IDs are reused when the student already has one, and minted only when they do not.
        student_id = own_student_id.get(email) or next_student_id(used_student_ids)
        if student_id_column is not None:
            row[student_id_column] = student_id
        passport_id = own_passport_id.get(email) or award.passport_id.strip()
        if passport_column is not None:
            row[passport_column] = passport_id
        values.update(
            email=email,
            skill=award.skill_name,
            skill_id=award.skill_id,
            skill_category=award.category,
            badge=award.badge,
            description=award.description,
            awarded_on=award.awarded_on,
        )
        for field, value in values.items():
            target = columns.get(field)
            if target is not None:
                row[target] = value
        if record_column is not None:
            highest_record += 1
            row[record_column] = f"REC-{highest_record:04d}"
        rows.append(row)
        placements.append(AwardPlacement(email, first_row + len(rows) - 1, ""))
        # The same email twice in one request must not write the same skill twice.
        awarded.add((email, award.skill_id.upper()))
        awarded.add((email, award.skill_name.lower()))
        earlier[email] = list(row)
        used_student_ids.add(student_id)
        own_student_id[email] = student_id
        if passport_id:
            own_passport_id[email] = passport_id
    return rows, placements
